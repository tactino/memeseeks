"""Chinese-CLIP image and text embeddings (text queries in Chinese, images of any language)."""

from __future__ import annotations

import numpy as np


class ChineseClip:
    def __init__(self, model_id: str = "OFA-Sys/chinese-clip-vit-large-patch14-336px", device: str | None = None):
        import torch
        from transformers import ChineseCLIPModel, ChineseCLIPProcessor

        self._torch = torch
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model = ChineseCLIPModel.from_pretrained(model_id).to(self.device).eval()
        self.processor = ChineseCLIPProcessor.from_pretrained(model_id)

    def _normalize(self, feats) -> np.ndarray:
        return self._torch.nn.functional.normalize(feats, dim=-1).float().cpu().numpy()

    def embed_images(self, images, batch_size: int = 16) -> np.ndarray:
        chunks = []
        with self._torch.no_grad():
            for i in range(0, len(images), batch_size):
                inputs = self.processor(images=images[i:i + batch_size], return_tensors="pt").to(self.device)
                chunks.append(self._normalize(self.model.get_image_features(**inputs)))
        return np.concatenate(chunks) if chunks else np.zeros((0, self.model.config.projection_dim), np.float32)

    def embed_texts(self, texts, batch_size: int = 64) -> np.ndarray:
        chunks = []
        with self._torch.no_grad():
            for i in range(0, len(texts), batch_size):
                inputs = self.processor(text=texts[i:i + batch_size], padding=True, truncation=True,
                                        max_length=52, return_tensors="pt").to(self.device)
                # Not get_text_features(): transformers 4.57 builds the text tower without a pooler and then
                # reads pooler_output (None). Chinese-CLIP's text feature is the projected CLS hidden state.
                hidden = self.model.text_model(**inputs).last_hidden_state
                chunks.append(self._normalize(self.model.text_projection(hidden[:, 0, :])))
        return np.concatenate(chunks) if chunks else np.zeros((0, self.model.config.projection_dim), np.float32)
