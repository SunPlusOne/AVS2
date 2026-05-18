import torch
import torch.nn as nn


class CrossModalMixer(nn.Module):
    def __init__(self, dim=256, n_heads=8, qkv_bias=False, dropout=0.):
        super().__init__()

        self.dim = dim
        self.n_heads = n_heads
        self.dropout = dropout
        self.scale = (dim // n_heads)**-0.5

        self.q_proj = nn.Linear(dim, dim, bias=qkv_bias)
        self.kv_proj = nn.Linear(dim, dim * 2, bias=qkv_bias)
        self.attn_drop = nn.Dropout(dropout)
        self.proj = nn.Linear(dim, dim)
        self.proj_drop = nn.Dropout(dropout)

    def forward(self, feature_map, audio_feature):
        """channel attention for modality fusion

        Args:
            feature_map (Tensor): (bs, c, h, w)
            audio_feature (Tensor): (bs, 1, c)

        Returns:
            Tensor: (bs, c, h, w)
        """
        flatten_map = feature_map.flatten(2).transpose(1, 2)
        B, N, C = flatten_map.shape

        q = self.q_proj(audio_feature).reshape(
            B, 1, self.n_heads, C // self.n_heads).permute(0, 2, 1, 3)
        kv = self.kv_proj(flatten_map).reshape(
            B, N, 2, self.n_heads, C // self.n_heads).permute(2, 0, 3, 1, 4)
        k, v = kv.unbind(0)
        attn = (q @ k.transpose(-2, -1)) * self.scale
        attn = attn.softmax(dim=-1)
        x = (attn @ v).transpose(1, 2).reshape(B, 1, C)
        x = self.proj_drop(self.proj(x))

        x = x.sigmoid()
        fusion_map = torch.einsum('bchw,bc->bchw', feature_map, x.squeeze())
        return fusion_map


class BidirectionalFusionModule(nn.Module):
    """COMBO-style bidirectional fusion module.

    It applies two cross-attentions:
    - visual tokens query audio tokens
    - audio tokens query visual tokens
    Then performs residual fusion for both streams.
    """

    def __init__(self, dim=256, n_heads=8, dropout=0.1):
        super().__init__()
        self.v_queries_a = nn.MultiheadAttention(
            dim, n_heads, dropout=dropout, batch_first=True)
        self.a_queries_v = nn.MultiheadAttention(
            dim, n_heads, dropout=dropout, batch_first=True)
        self.audio_to_visual = nn.Linear(dim, dim)
        self.v_norm = nn.LayerNorm(dim)
        self.a_norm = nn.LayerNorm(dim)
        self.dropout = nn.Dropout(dropout)

    def forward(self, visual_tokens, audio_tokens):
        # visual_tokens: [B, N, C], audio_tokens: [B, M, C]
        v_from_a = self.v_queries_a(visual_tokens, audio_tokens, audio_tokens)[0]
        a_from_v = self.a_queries_v(audio_tokens, visual_tokens, visual_tokens)[0]

        # Inject global audio-aware cue back to all visual tokens.
        audio_prompt = self.audio_to_visual(a_from_v.mean(dim=1, keepdim=True))
        visual_tokens = self.v_norm(
            visual_tokens + self.dropout(v_from_a) + self.dropout(audio_prompt))
        audio_tokens = self.a_norm(audio_tokens + self.dropout(a_from_v))
        return visual_tokens, audio_tokens


def build_fusion_block(type, **kwargs):
    if type == 'CrossModalMixer':
        return CrossModalMixer(**kwargs)
    elif type == 'BidirectionalFusionModule':
        return BidirectionalFusionModule(**kwargs)
    else:
        raise ValueError
