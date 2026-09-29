(() => {
  const PROTOCOL = "region-ann-v0";
  const UTC_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/;

  function questions() {
    const node = document.getElementById("pilot-questions");
    return JSON.parse(node.textContent);
  }

  function byId(id) {
    return document.getElementById(id);
  }

  function utcNow() {
    return new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
  }

  function legalIds(row) {
    return new Set((row.candidates || []).map((box) => Number(box.box_id)));
  }

  function parseNullableBool(value) {
    if (value === "null" || value === "" || value == null) return null;
    if (value === "true" || value === true) return true;
    if (value === "false" || value === false) return false;
    return undefined;
  }

  function setRadio(name, value) {
    const want = value === null || value === undefined ? "null" : String(value);
    for (const node of document.querySelectorAll(`input[name="${name}"]`)) {
      node.checked = node.value === want;
    }
  }

  function radioValue(name) {
    const node = document.querySelector(`input[name="${name}"]:checked`);
    return node ? node.value : "null";
  }

  function readQuestion(row) {
    const sid = row.sample_id;
    const chosen = [];
    const coverLevels = {};
    for (const box of row.candidates || []) {
      const bid = Number(box.box_id);
      const checked = byId(`box-${sid}-${bid}`);
      if (checked && checked.checked) chosen.push(bid);
      const level = byId(`cover-${sid}-${bid}`);
      if (checked && checked.checked && level && (level.value === "full" || level.value === "partial")) {
        coverLevels[String(bid)] = level.value;
      }
    }
    const noCandidate = byId(`nc-${sid}`).checked;
    return {
      chosen_box_ids: chosen,
      cover_levels: coverLevels,
      cover_ok: parseNullableBool(radioValue(`coverok-${sid}`)),
      no_candidate: noCandidate ? true : parseNullableBool(radioValue(`ncflag-${sid}`)),
      cross_box: parseNullableBool(radioValue(`cross-${sid}`)),
      remark: byId(`remark-${sid}`).value.trim(),
      label_status: radioValue(`status-${sid}`),
    };
  }

  function fillQuestion(row, rec) {
    const sid = row.sample_id;
    const chosen = new Set(rec.chosen_box_ids || []);
    const levels = rec.cover_levels || {};
    for (const box of row.candidates || []) {
      const bid = Number(box.box_id);
      const boxNode = byId(`box-${sid}-${bid}`);
      const levelNode = byId(`cover-${sid}-${bid}`);
      if (boxNode) boxNode.checked = chosen.has(bid);
      const raw = levels[String(bid)] ?? levels[bid];
      if (levelNode) levelNode.value = raw === "full" || raw === "partial" ? raw : "";
    }
    const nc = rec.no_candidate === true;
    byId(`nc-${sid}`).checked = nc;
    setRadio(`ncflag-${sid}`, rec.no_candidate === true ? true : rec.no_candidate === false ? false : null);
    setRadio(`coverok-${sid}`, rec.cover_ok);
    setRadio(`cross-${sid}`, rec.cross_box);
    byId(`remark-${sid}`).value = rec.remark || rec.note || "";
    const status = rec.label_status || "pending";
    setRadio(`status-${sid}`, status);
    syncNoCandidate(sid);
  }

  function syncNoCandidate(sid) {
    const nc = byId(`nc-${sid}`).checked;
    const form = document.querySelector(`section[data-sample-id="${sid}"]`);
    if (!form) return;
    for (const node of form.querySelectorAll("input.box-check, select.cover-level")) {
      node.disabled = nc;
    }
    if (nc) {
      for (const node of form.querySelectorAll("input.box-check")) node.checked = false;
      for (const node of form.querySelectorAll("select.cover-level")) node.value = "";
      setRadio(`coverok-${sid}`, false);
      setRadio(`cross-${sid}`, false);
      setRadio(`ncflag-${sid}`, true);
      setRadio(`status-${sid}`, "skipped");
    } else {
      setRadio(`ncflag-${sid}`, parseNullableBool(radioValue(`ncflag-${sid}`)));
    }
  }

  function validateRecord(row, rec, annotator) {
    const errors = [];
    const sid = row.sample_id;
    const legal = legalIds(row);
    const chosen = rec.chosen_box_ids;
    if (!Array.isArray(chosen)) {
      errors.push(`${sid}: chosen_box_ids 必须是数组`);
      return errors;
    }
    const seen = new Set();
    for (const bid of chosen) {
      if (!Number.isInteger(bid) || bid < 0) errors.push(`${sid}: 非法 box_id ${bid}`);
      else if (!legal.has(bid)) errors.push(`${sid}: box_id ${bid} 不在本页候选中`);
      if (seen.has(bid)) errors.push(`${sid}: 重复 box_id ${bid}`);
      seen.add(bid);
    }
    const levels = rec.cover_levels || {};
    if (typeof levels !== "object" || Array.isArray(levels)) {
      errors.push(`${sid}: cover_levels 必须是对象`);
    } else {
      for (const [key, value] of Object.entries(levels)) {
        const bid = Number(key);
        if (!Number.isInteger(bid) || !legal.has(bid)) errors.push(`${sid}: cover_levels 含非法键 ${key}`);
        if (value !== "full" && value !== "partial") errors.push(`${sid}: cover_levels[${key}] 只能是 full 或 partial`);
        if (!seen.has(bid)) errors.push(`${sid}: cover_levels 只能写已选框，${key} 未选`);
      }
    }
    if (![true, false, null].includes(rec.cover_ok)) errors.push(`${sid}: cover_ok 必须是 true / false / null`);
    if (![true, false, null].includes(rec.no_candidate)) errors.push(`${sid}: no_candidate 必须是 true / false / null`);
    if (![true, false, null].includes(rec.cross_box)) errors.push(`${sid}: cross_box 必须是 true / false / null`);
    if (!["pending", "labeled", "skipped", "adjudicated"].includes(rec.label_status)) {
      errors.push(`${sid}: 非法 label_status`);
    }
    if (rec.no_candidate === true && chosen.length) {
      errors.push(`${sid}: 无合适候选时不能再选框`);
    }
    if (rec.no_candidate === true && rec.cover_ok === true) {
      errors.push(`${sid}: 无合适候选时 cover_ok 不能为 true`);
    }
    if (rec.no_candidate === true && rec.label_status !== "skipped") {
      errors.push(`${sid}: 无合适候选必须是 skipped，不能保持 pending，也不能标成 labeled`);
    }
    if (rec.label_status === "pending" && rec.no_candidate === true) {
      errors.push(`${sid}: 不确定必须保持 pending，不能改成 no_candidate`);
    }
    if (rec.label_status === "labeled") {
      if (!chosen.length) errors.push(`${sid}: labeled 必须选择至少一个框`);
      if (rec.no_candidate === true) errors.push(`${sid}: labeled 不能同时 no_candidate`);
      if (rec.cover_ok === null) errors.push(`${sid}: labeled 必须判断 cover_ok`);
      if (chosen.length >= 2 && rec.cross_box !== true) errors.push(`${sid}: 选了多个框时必须 cross_box=true`);
      if (chosen.length === 1 && rec.cross_box === true) errors.push(`${sid}: 只选一个框时不能 cross_box=true`);
    }
    if (rec.label_status === "skipped") {
      if (rec.no_candidate !== true) errors.push(`${sid}: skipped 必须 no_candidate=true`);
      if (chosen.length) errors.push(`${sid}: skipped 不能有 chosen_box_ids`);
    }
    if (rec.label_status === "pending") {
      if (rec.labeled_at != null && rec.labeled_at !== "") {
        errors.push(`${sid}: pending 的 labeled_at 必须为空`);
      }
    } else if (rec.labeled_at != null && rec.labeled_at !== "" && !UTC_RE.test(String(rec.labeled_at))) {
      errors.push(`${sid}: labeled_at 必须是 UTC，例如 2026-09-29T10:19:36Z`);
    }
    if (annotator && rec.annotator && rec.annotator !== annotator) {
      errors.push(`${sid}: 记录里的 annotator=${rec.annotator} 与当前会话 ${annotator} 不一致`);
    }
    return errors;
  }

  function parseJsonl(text) {
    const rows = [];
    for (const line of text.split(/\r?\n/)) {
      if (!line.trim()) continue;
      rows.push(JSON.parse(line));
    }
    return rows;
  }

  function toJsonl(rows) {
    return rows.map((row) => JSON.stringify(row)).join("\n") + "\n";
  }

  function download(name, text) {
    const blob = new Blob([text], { type: "application/jsonl;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    a.click();
    URL.revokeObjectURL(url);
  }

  function showStatus(text, isError) {
    const node = byId("io-status");
    node.textContent = text;
    node.className = isError ? "err" : "ok";
  }

  function currentAnnotator() {
    const value = byId("session-annotator").value;
    if (value !== "A" && value !== "B") throw new Error("请先选择标注者 A 或 B");
    return value;
  }

  function mergeImported(imported) {
    const q = questions();
    const map = new Map();
    for (const rec of imported) {
      if (!rec || !rec.sample_id) continue;
      if (map.has(rec.sample_id)) throw new Error(`导入文件有重复题目 ${rec.sample_id}`);
      map.set(rec.sample_id, rec);
    }
    const extra = [...map.keys()].filter((sid) => !q.some((row) => row.sample_id === sid));
    if (extra.length) throw new Error(`导入文件含本工作簿没有的题目：${extra.join(", ")}`);
    for (const row of q) {
      fillQuestion(row, map.get(row.sample_id) || { chosen_box_ids: [], cover_levels: {}, cover_ok: null, no_candidate: null, cross_box: null, remark: "", label_status: "pending" });
    }
    const importedAnnotator = imported.find((rec) => rec.annotator === "A" || rec.annotator === "B");
    if (importedAnnotator) byId("session-annotator").value = importedAnnotator.annotator;
  }

  function collectRows(stampUtc) {
    const annotator = currentAnnotator();
    const q = questions();
    const out = [];
    const errors = [];
    for (const row of q) {
      const rec = { ...row, ...readQuestion(row) };
      rec.annotator = annotator;
      rec.annotator_id = annotator;
      rec.protocol_version = PROTOCOL;
      rec.note = rec.remark || "";
      if (rec.label_status === "pending") rec.labeled_at = null;
      else rec.labeled_at = stampUtc;
      errors.push(...validateRecord(row, rec, annotator));
      out.push(rec);
    }
    return { out, errors, annotator };
  }

  function countStatus(rows) {
    const counts = { pending: 0, labeled: 0, skipped: 0, adjudicated: 0 };
    for (const rec of rows) {
      if (counts[rec.label_status] != null) counts[rec.label_status] += 1;
    }
    return counts;
  }

  async function importFile(file) {
    const text = await file.text();
    mergeImported(parseJsonl(text));
    showStatus(`已导入 ${file.name}。浏览器不会写回磁盘，导出后请另存为 labels_annotator_A.jsonl 或 labels_annotator_B.jsonl。`, false);
  }

  function exportFile() {
    const stamp = utcNow();
    const { out, errors, annotator } = collectRows(stamp);
    if (errors.length) {
      showStatus(errors.join("\n"), true);
      return;
    }
    const counts = countStatus(out);
    const name = `labels_annotator_${annotator}.jsonl`;
    download(name, toJsonl(out));
    showStatus(
      `已下载 ${name}。UTC=${stamp}。pending=${counts.pending} labeled=${counts.labeled} skipped=${counts.skipped}。浏览器没有写回仓库里的原文件，请把下载文件覆盖到 experiments/region_annotation/。`,
      false
    );
  }

  function checkNow() {
    const stamp = utcNow();
    const { out, errors } = collectRows(stamp);
    const counts = countStatus(out);
    if (errors.length) showStatus(errors.join("\n"), true);
    else showStatus(`校验通过。pending=${counts.pending} labeled=${counts.labeled} skipped=${counts.skipped}。尚未保存到磁盘。`, false);
  }

  function bind() {
    byId("btn-import").addEventListener("click", () => byId("file-import").click());
    byId("file-import").addEventListener("change", (ev) => {
      const file = ev.target.files && ev.target.files[0];
      if (file) importFile(file).catch((err) => showStatus(String(err.message || err), true));
      ev.target.value = "";
    });
    byId("btn-export").addEventListener("click", () => {
      try {
        exportFile();
      } catch (err) {
        showStatus(String(err.message || err), true);
      }
    });
    byId("btn-check").addEventListener("click", () => {
      try {
        checkNow();
      } catch (err) {
        showStatus(String(err.message || err), true);
      }
    });
    document.addEventListener("change", (ev) => {
      const node = ev.target;
      if (node && node.classList.contains("nc-check")) syncNoCandidate(node.getAttribute("data-sample-id"));
    });
  }

  bind();
})();
