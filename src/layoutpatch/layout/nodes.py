"""Layout node encoder (PAPER_SPEC 5.2), shared by shape tests and fusion runs.

Recorded interface:
- text input: [B, M, text_dim], text_dim is caller-supplied; this repo has no
  frozen OCR embedding width, so the module does not assume one.
- coordinates: [B, M, 6], normalized [x1/W, y1/H, x2/W, y2/H, w/W, h/H].
- type encoding: integer IDs into a learned embedding; ID 0 is UNK.
- empty text: an all-zero text vector. It still passes through Linear.
- no evaluation gold is accepted as an input.
"""

from __future__ import annotations

import torch
from torch import nn

D = 128
COORD_DIM = 6
UNK_TYPE_ID = 0


def sinusoidal_coord(coords: torch.Tensor, width: int) -> torch.Tensor:
    """Sine/cosine over the six normalized coordinates."""
    if width % (2 * COORD_DIM) != 0:
        raise ValueError(f"coord width {width} must be divisible by {2 * COORD_DIM}")
    bands = width // (2 * COORD_DIM)
    frequencies = torch.arange(bands, device=coords.device, dtype=coords.dtype)
    scale = torch.pow(torch.tensor(10000.0, device=coords.device, dtype=coords.dtype), -frequencies / bands)
    angles = coords.unsqueeze(-1) * scale
    return torch.cat((angles.sin(), angles.cos()), dim=-1).flatten(-2)


class TextLayoutEncoder(nn.Module):
    """Encode text, coordinates, and type separately, then project to D=128."""

    def __init__(self, text_dim: int, num_types: int, coord_width: int = 72) -> None:
        super().__init__()
        if text_dim <= 0 or num_types <= 1:
            raise ValueError("text_dim must be positive and num_types must include UNK plus one type")
        self.text_proj = nn.Linear(text_dim, D)
        self.coord_proj = nn.Linear(coord_width, D)
        self.type_emb = nn.Embedding(num_types, D, padding_idx=UNK_TYPE_ID)
        self.fuse = nn.Linear(3 * D, D)
        self.coord_width = coord_width

    def forward(
        self,
        text: torch.Tensor,
        coords: torch.Tensor,
        type_ids: torch.Tensor,
        valid_mask: torch.Tensor,
    ) -> torch.Tensor:
        if text.shape[-1] != self.text_proj.in_features or coords.shape[-1] != COORD_DIM:
            raise ValueError("text or coordinate width does not match the recorded interface")
        text_h = self.text_proj(text)
        coord_h = self.coord_proj(sinusoidal_coord(coords, self.coord_width))
        type_h = self.type_emb(type_ids.long())
        nodes = self.fuse(torch.cat((text_h, coord_h, type_h), dim=-1))
        return torch.nn.functional.normalize(nodes, dim=-1) * valid_mask.unsqueeze(-1).to(nodes.dtype)
