"""Page-only OCR interfaces. No model loading, downloads, or scoring imports."""
import hashlib
import json
import math
import re
import time
from contextlib import contextmanager
from pathlib import Path, PureWindowsPath

from PIL import Image

POLICY = 'deepseek-ocr2-grounding-v1'
INFER = dict(prompt='<image>\n<|grounding|>Convert the document to markdown.',
             base_size=1024, image_size=768, crop_mode=True,
             eval_mode=True, save_results=False, test_compress=False)
MARKERS = re.compile(r'<\|/?(?:ref|det)\|>')
BLOCK = re.compile(r'<\|ref\|>([^<>]+)<\|/ref\|>\s*<\|det\|>(.*?)<\|/det\|>', re.S)
LABELS = {**dict.fromkeys(['text', 'paragraph', 'caption', 'footnote',
    'image_caption', 'image_footnote', 'table_caption', 'table_footnote',
    'chart_caption', 'chart_footnote', 'code_caption', 'code_footnote'], 'text'),
    **dict.fromkeys(['title', 'sub_title'], 'title'),
    **dict.fromkeys(['image', 'figure', 'chart'], 'image'),
    'table': 'table', 'equation': 'equation', 'interline_equation': 'equation'}


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_json(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def dimensions(size):
    require(isinstance(size, (list, tuple)) and len(size) == 2 and
            all(type(v) is int and v > 0 for v in size), 'invalid page dimensions')


def source_path(windows_path, source_root):
    """Only permit paths under the original project's artifacts directory."""
    original = PureWindowsPath('C:/Users/WenJing/Documents/WorkTransfer/layoutpatch')
    relative = PureWindowsPath(windows_path).relative_to(original)
    require(relative.parts[0] == 'artifacts' and '..' not in relative.parts, 'unsafe source path')
    root = Path(source_root).resolve()
    target = root.joinpath(*relative.parts).resolve()
    require(target.is_relative_to(root), 'source escaped mount')
    return target


def prepare_page(row, source_root):
    """Validate page identity and mapping; only return parser image + geometry."""
    require(set(row) == {'smoke_order', 'page_id', 'purpose', 'effect_evaluation_enabled',
            'parser_input', 'evaluation_reference', 'question_answer_gold_provided'}, 'unexpected manifest fields')
    require(row['question_answer_gold_provided'] is False and
            row['effect_evaluation_enabled'] is False, 'not a page-only technical manifest')
    require(re.fullmatch(r'[A-Za-z0-9_.-]+', row['page_id']) is not None, 'unsafe page id')
    inp, ref = row['parser_input'], row['evaluation_reference']
    require(set(inp) == {'image_path', 'sha256', 'size', 'exif_orientation'}, 'unexpected parser input')
    require(set(ref) == {'render_path', 'sha256', 'page_size', 'pdf_rotation',
                        'mapping_status', 'receipt_path', 'receipt_sha256', 'P_sha256'}, 'unexpected reference')
    dimensions(inp['size']); dimensions(ref['page_size'])
    image = source_path(inp['image_path'], source_root)
    render = source_path(ref['render_path'], source_root)
    receipt_path = source_path(ref['receipt_path'], source_root)
    for path, expected in [(image, inp['sha256']), (render, ref['sha256']),
                           (receipt_path, ref['receipt_sha256'])]:
        require(sha(path) == expected, f'input hash mismatch: {path.name}')
    receipt = json.loads(receipt_path.read_text(encoding='utf-8-sig'))
    mapping = receipt['image']['mapping']
    require(receipt['page_id'] == row['page_id'] and receipt['status'] == 'passed' and
            mapping['status'] == ref['mapping_status'] == 'passed', 'unverified source/render mapping')
    require(receipt['image']['sha256'] == inp['sha256'] and
            receipt['render']['render_sha256'] == ref['sha256'] and
            mapping['source_image_size'] == inp['size'] and
            mapping['render_image_size'] == ref['page_size'] and
            receipt['render']['page_size'] == ref['page_size'] and
            receipt['render']['rotation'] == ref['pdf_rotation'], 'receipt identity mismatch')
    require(inp['exif_orientation'] == mapping['source_exif_orientation'] == 1,
            'v1 requires already oriented source; no implicit EXIF conversion')
    with Image.open(image) as im:
        require(list(im.size) == inp['size'] and im.getexif().get(274, 1) == 1, 'image geometry mismatch')
    with Image.open(image) as im:
        im.verify()
    with Image.open(render) as im:
        require(list(im.size) == ref['page_size'], 'render geometry mismatch')
        im.verify()
    require(inp['size'][0] * ref['page_size'][1] == inp['size'][1] * ref['page_size'][0],
            'v1 requires equal source/render aspect ratio')
    return dict(page_id=row['page_id'], image_path=str(image), image_sha256=inp['sha256'],
                source_size=inp['size'], page_size=ref['page_size'], exif_orientation=1,
                mapping_receipt_sha256=ref['receipt_sha256'], render_sha256=ref['sha256'],
                transform='oriented_full_image_999_to_render_pixels_no_extra_rotation',
                pdf_rotation_diagnostic_only=ref['pdf_rotation'])


def export_grounding(raw, page_id, page_size):
    """All-or-nothing parsing; ordinary Markdown never creates candidates."""
    require(isinstance(raw, str), 'raw output is not text')
    dimensions(page_size)
    matches = list(BLOCK.finditer(raw))
    remaining = BLOCK.sub('', raw)
    require(not MARKERS.search(remaining) and '<|ref' not in remaining and '<|det' not in remaining
            and '<|/ref' not in remaining and '<|/det' not in remaining, 'malformed grounding markers')
    raw_hash = hashlib.sha256(raw.encode('utf-8')).hexdigest()
    if not matches:
        return dict(status='no_grounding', candidates=[], raw_sha256=raw_hash, policy=POLICY)
    rows, seen = [], {}
    for ri, match in enumerate(matches):
        label = match.group(1).strip()
        require(bool(label), 'empty label')
        boxes = json.loads(match.group(2))
        require(isinstance(boxes, list) and len(boxes) > 0, 'empty or invalid det list')
        stop = matches[ri + 1].start() if ri + 1 < len(matches) else len(raw)
        text = raw[match.end():stop]
        for bi, box in enumerate(boxes):
            require(isinstance(box, list) and len(box) == 4 and all(
                type(v) in (int, float) and math.isfinite(v) for v in box), 'invalid numeric box')
            x1, y1, x2, y2 = box
            require(0 <= x1 < x2 <= 999 and 0 <= y1 < y2 <= 999, 'empty or out-of-bounds box')
            candidate_id = f'{POLICY}:{page_id}:{ri}:{bi}'
            origin = dict(candidate_id=candidate_id, ref_index=ri, box_index=bi,
                          raw_label=label, raw_bbox=box, ref_char_span=[match.start(), match.end()],
                          text_char_span=[match.end(), stop], text=text,
                          shared_text_group=f'{page_id}:ref:{ri}')
            key = tuple(box)
            if key in seen:
                rows[seen[key]]['aliases'].append(origin)
                continue
            node_type = LABELS.get(label.lower(), 'UNK')
            seen[key] = len(rows)
            rows.append(dict(candidate_id=candidate_id, layout_id=len(rows), page_id=page_id,
                             page_size=list(page_size), bbox=[x1/999*page_size[0], y1/999*page_size[1],
                             x2/999*page_size[0], y2/999*page_size[1]], type=node_type,
                             type_id={'UNK':0,'text':1,'title':2,'table':3,'image':4,'equation':5}[node_type],
                             unknown_label=node_type == 'UNK', text=text, source=origin,
                             aliases=[], raw_sha256=raw_hash, policy=POLICY))
    return dict(status='exported', candidates=rows, raw_sha256=raw_hash, policy=POLICY,
                raw_box_count=sum(len(r['aliases']) + 1 for r in rows))


def tensor_metadata(value):
    if hasattr(value, 'shape'):
        return dict(shape=list(value.shape), dtype=str(value.dtype), device=str(value.device))
    if isinstance(value, (tuple, list)):
        return [tensor_metadata(v) for v in value]
    if value is None or type(value) in (int, float, bool, str):
        return value
    raise ValueError(f'unrecordable generate argument: {type(value).__name__}')


@contextmanager
def observe_generate(model, records):
    """Preserve arguments and returned object; record token IDs, not retokenized text."""
    original = model.generate
    had_override = 'generate' in vars(model)
    override = vars(model).get('generate')

    def observed(*args, **kwargs):
        record = dict(status='started', args=[tensor_metadata(a) for a in args],
                      kwargs={k: tensor_metadata(v) for k, v in kwargs.items()})
        records.append(record)
        started = time.monotonic()
        try:
            output = original(*args, **kwargs)
            ids = args[0] if args else kwargs['input_ids']
            sequences = output.sequences if hasattr(output, 'sequences') else output
            require(len(ids.shape) == len(sequences.shape) == 2 and ids.shape[0] == sequences.shape[0] == 1,
                    'observer requires single sequence')
            prefix = ids[0].tolist()
            all_ids = sequences[0].tolist()
            require(all_ids[:len(prefix)] == prefix, 'generated prefix differs from input')
            new_ids = all_ids[len(prefix):]
            limit = kwargs.get('max_new_tokens')
            eos = kwargs.get('eos_token_id')
            eos_ids = [eos] if type(eos) is int else eos
            require(type(limit) is int and limit > 0 and isinstance(eos_ids, (list, tuple))
                    and all(type(v) is int for v in eos_ids), 'unverifiable generation limit/EOS')
            hit_limit = len(new_ids) >= limit
            terminal_eos = bool(new_ids) and new_ids[-1] in eos_ids
            early_eos = any(v in eos_ids for v in new_ids[:-1])
            status = 'limit_reached' if hit_limit else ('eos' if terminal_eos and not early_eos else 'termination_unproven')
            record.update(status=status, input_tokens=len(prefix), new_tokens=len(new_ids),
                          new_token_ids=new_ids, last_token=new_ids[-1] if new_ids else None,
                          eos_token_ids=list(eos_ids), terminal_eos=terminal_eos,
                          reached_limit=hit_limit, early_eos=early_eos)
            return output
        except Exception as exc:
            record.update(status='error', error_type=type(exc).__name__, error=str(exc))
            raise
        finally:
            record['elapsed_seconds'] = time.monotonic() - started

    model.generate = observed
    try:
        yield
    finally:
        if had_override:
            model.generate = override
        else:
            delattr(model, 'generate')


def process_page(model, tokenizer, page, output_root):
    """Injected already-loaded model only; creates a new page directory, never retries.

    Caller owns model hash/load/resource checks and an external process timeout.
    This function cannot load a model and does not accept questions/answers/gold.
    """
    require(set(page) == {'page_id', 'image_path', 'image_sha256', 'source_size', 'page_size',
            'exif_orientation', 'mapping_receipt_sha256', 'render_sha256', 'transform',
            'pdf_rotation_diagnostic_only'}, 'unexpected page contract')
    require(re.fullmatch(r'[A-Za-z0-9_.-]+', page['page_id']) is not None, 'unsafe page id')
    root = Path(output_root).resolve()
    require(root.is_dir(), 'output root must already exist')
    out = root / page['page_id']
    out.mkdir(exist_ok=False)
    records = []
    receipt = dict(status='started', page=page, infer_parameters=INFER, generation=records,
                   started_at=time.time(), attempts=1, inference_executed=False)
    write_json(out / 'started.json', receipt)
    try:
        require(sha(page['image_path']) == page['image_sha256'], 'input changed before inference')
        receipt['inference_executed'] = True
        with observe_generate(model, records):
            raw = model.infer(tokenizer, image_file=page['image_path'],
                              output_path=str(out / 'upstream'), **INFER)
        require(isinstance(raw, str), 'infer did not return raw text')
        with (out / 'raw.txt').open('x', encoding='utf-8', newline='') as stream:
            stream.write(raw)
        receipt['raw_sha256'] = sha(out / 'raw.txt')
        write_json(out / 'generation.json', records)
        require(len(records) == 1 and records[0]['status'] == 'eos', 'generation termination not accepted')
        require(records[0]['kwargs'].get('max_new_tokens') == 8192 and
                records[0]['kwargs'].get('temperature') == 0.0 and
                records[0]['kwargs'].get('no_repeat_ngram_size') == 35 and
                records[0]['kwargs'].get('use_cache') is True, 'upstream generation parameters changed')
        result = export_grounding(raw, page['page_id'], page['page_size'])
        write_json(out / 'candidates.json', result)
        receipt.update(status=result['status'], candidate_count=len(result['candidates']),
                       candidates_sha256=sha(out / 'candidates.json'))
    except Exception as exc:
        receipt.update(status='failed', error_type=type(exc).__name__, error=str(exc))
    finally:
        receipt['finished_at'] = time.time()
        receipt['continue_allowed'] = receipt['status'] == 'exported'
        write_json(out / 'receipt.json', receipt)
    return receipt


def process_sequence(model, tokenizer, pages, output_root):
    """Sequential interface; persist every planned page including not_attempted.

    Run only inside the caller's supervised process; no model-load facility here.
    """
    ids = [p['page_id'] for p in pages]
    require(len(set(ids)) == len(ids), 'duplicate planned page')
    root = Path(output_root)
    status_path = root / 'page_status.json'
    statuses = [dict(page_id=p, status='not_attempted') for p in ids]
    write_json(status_path, statuses)
    def checkpoint():
        temp = root / 'page_status.next.json'
        write_json(temp, statuses)
        temp.replace(status_path)
    for i, page in enumerate(pages):
        statuses[i]['status'] = 'running'
        checkpoint()
        try:
            receipt = process_page(model, tokenizer, page, root)
            statuses[i]['status'] = receipt['status']
            proceed = receipt['continue_allowed']
        except Exception as exc:
            statuses[i].update(status='failed', error=str(exc), error_type=type(exc).__name__)
            proceed = False
        checkpoint()
        if not proceed:
            break
    return statuses
