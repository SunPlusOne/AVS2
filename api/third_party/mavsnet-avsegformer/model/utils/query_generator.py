import torch
import torch.nn as nn
import torch.nn.functional as F


class RepeatGenerator(nn.Module):
    def __init__(self, query_num) -> None:
        super().__init__()
        self.query_num = query_num

    def forward(self, visual_feat, audio_feat=None):
        if audio_feat is None:
            audio_feat = visual_feat
        return audio_feat.repeat(1, self.query_num, 1)


class AttentionLayer(nn.Module):
    def __init__(self, embed_dim, num_heads, hidden_dim) -> None:
        super().__init__()
        self.self_attn = nn.MultiheadAttention(
            embed_dim, num_heads, bias=False, batch_first=True)
        self.cross_attn = nn.MultiheadAttention(
            embed_dim, num_heads, bias=False, batch_first=True)
        self.ffn = nn.Sequential(
            nn.Linear(embed_dim, hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, embed_dim)
        )
        self.norm1 = nn.LayerNorm(embed_dim)
        self.norm2 = nn.LayerNorm(embed_dim)
        self.norm3 = nn.LayerNorm(embed_dim)

    def forward(self, query, audio_feat):
        out1 = self.self_attn(query, query, query)[0]
        query = self.norm1(query+out1)
        out2 = self.cross_attn(query, audio_feat, audio_feat)[0]
        query = self.norm2(query+out2)
        out3 = self.ffn(query)
        query = self.norm3(query+out3)
        return query


class AttentionGenerator(nn.Module):
    def __init__(self, num_layers, query_num, embed_dim=256, num_heads=8, hidden_dim=1024):
        super().__init__()
        self.num_layers = num_layers
        self.query_num = query_num
        self.embed_dim = embed_dim
        self.query = nn.Embedding(query_num, embed_dim)
        self.layers = nn.ModuleList(
            [AttentionLayer(embed_dim, num_heads, hidden_dim)
             for i in range(num_layers)]
        )

        self._reset_parameters()

    def _reset_parameters(self):
        for p in self.parameters():
            if p.dim() > 1:
                nn.init.xavier_uniform_(p)

    def forward(self, visual_feat, audio_feat=None):
        if audio_feat is None:
            audio_feat = visual_feat
        bs = audio_feat.shape[0]
        query = self.query.weight[None, :, :].repeat(bs, 1, 1)
        for layer in self.layers:
            query = layer(query, audio_feat)
        return query


class PromptedVisualQueryGenerator(nn.Module):
    """VCT-style prompted query generator.

    1) Build visual-centered initial queries from visual tokens using lightweight 1D pooling.
    2) Build audio prototypes with one shallow cross-attention from prototype seeds.
    3) Inject audio prototypes into visual queries by element-wise add as prompt.
    """

    def __init__(self, query_num, prototype_num=8, embed_dim=256, num_heads=8, dropout=0.1):
        super().__init__()
        self.query_num = query_num
        self.prototype_num = prototype_num
        self.prototype_seed = nn.Embedding(prototype_num, embed_dim)
        self.audio_proto_attn = nn.MultiheadAttention(
            embed_dim, num_heads, dropout=dropout, batch_first=True)
        self.norm_q = nn.LayerNorm(embed_dim)
        self.norm_p = nn.LayerNorm(embed_dim)

    @staticmethod
    def _resize_token_sequence(feat, out_len):
        """Resize token sequence along length dimension with linear interpolation.

        This avoids AdaptiveAvgPool kernels that can be unstable on some
        torch/cuda combinations while keeping differentiable behavior.
        """
        if feat.size(1) == out_len:
            return feat
        feat = F.interpolate(feat.transpose(1, 2), size=out_len,
                             mode='linear', align_corners=False)
        return feat.transpose(1, 2)

    def forward(self, visual_feat, audio_feat=None):
        if audio_feat is None:
            raise ValueError('PromptedVisualQueryGenerator requires audio_feat input.')

        # visual_feat: [B, S, C] -> [B, N, C]
        visual_query = self._resize_token_sequence(visual_feat, self.query_num)
        visual_query = self.norm_q(visual_query)

        # audio prototypes: [B, K, C] from shallow cross-attention
        bs = audio_feat.shape[0]
        proto_seed = self.prototype_seed.weight.unsqueeze(0).repeat(bs, 1, 1)
        audio_proto = self.audio_proto_attn(proto_seed, audio_feat, audio_feat)[0]
        audio_proto = self.norm_p(audio_proto)

        # prompt injection by element-wise add
        prompt = self._resize_token_sequence(audio_proto, self.query_num)
        prompted_query = visual_query + prompt
        return prompted_query


def build_generator(type, **kwargs):
    if type == 'AttentionGenerator':
        return AttentionGenerator(**kwargs)
    elif type == 'RepeatGenerator':
        return RepeatGenerator(**kwargs)
    elif type == 'PromptedVisualQueryGenerator':
        return PromptedVisualQueryGenerator(**kwargs)
    else:
        raise ValueError
