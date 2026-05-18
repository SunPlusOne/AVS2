import torch
import torch.nn as nn
import torch.nn.functional as F


def F5_IoU_BCELoss(pred_mask, five_gt_masks):
    """
    binary cross entropy loss (iou loss) of the total five frames for multiple sound source segmentation

    Args:
    pred_mask: predicted masks for a batch of data, shape:[bs*5, 1, 224, 224]
    five_gt_masks: ground truth mask of the total five frames, shape: [bs*5, 1, 224, 224]
    """
    assert len(pred_mask.shape) == 4
    pred_mask = torch.sigmoid(pred_mask)  # [bs*5, 1, 224, 224]
    # five_gt_masks = five_gt_masks.view(-1, 1, five_gt_masks.shape[-2], five_gt_masks.shape[-1]) # [bs*5, 1, 224, 224]
    loss = nn.BCELoss()(pred_mask, five_gt_masks)

    return loss


def F5_Dice_loss(pred_mask, five_gt_masks):
    """dice loss for aux loss

    Args:
        pred_mask (Tensor): (bs, 1, h, w)
        five_gt_masks (Tensor): (bs, 1, h, w)
    """
    assert len(pred_mask.shape) == 4
    pred_mask = torch.sigmoid(pred_mask)

    pred_mask = pred_mask.flatten(1)
    gt_mask = five_gt_masks.flatten(1)
    a = (pred_mask * gt_mask).sum(-1)
    b = (pred_mask * pred_mask).sum(-1) + 0.001
    c = (gt_mask * gt_mask).sum(-1) + 0.001
    d = (2 * a) / (b + c)
    loss = 1 - d
    return loss.mean()


def AdaptiveTemporalConsistencyLoss(pred_mask, gt_mask, batch_size, frame_num, alpha=5.0):
    """Adaptive frame consistency loss for MS3.

    The temporal smoothness term is adaptively weighted by GT inter-frame changes:
    larger GT changes -> smaller smoothness weight.
    """
    if frame_num <= 1:
        return pred_mask.new_tensor(0.0)

    pred_prob = torch.sigmoid(pred_mask).view(batch_size, frame_num, 1,
                                              pred_mask.shape[-2], pred_mask.shape[-1])
    gt_seq = gt_mask.view(batch_size, frame_num, 1,
                          gt_mask.shape[-2], gt_mask.shape[-1])

    pred_diff = torch.abs(pred_prob[:, 1:] - pred_prob[:, :-1]).mean(dim=(2, 3, 4))
    gt_diff = torch.abs(gt_seq[:, 1:] - gt_seq[:, :-1]).mean(dim=(2, 3, 4))
    adaptive_weight = torch.exp(-alpha * gt_diff)

    return (adaptive_weight * pred_diff).mean()


def IouSemanticAwareLoss(pred_mask, mask_feature, gt_mask, weight_dict, loss_type='bce', **kwargs):
    total_loss = 0
    loss_dict = {}

    if loss_type == 'bce':
        def loss_func(pred, gt):
            return F5_IoU_BCELoss(pred, gt)
    elif loss_type == 'dice':
        def loss_func(pred, gt):
            return F5_Dice_loss(pred, gt)
    elif loss_type == 'bce_dice':
        def loss_func(pred, gt):
            return 0.5 * (F5_IoU_BCELoss(pred, gt) + F5_Dice_loss(pred, gt))
    else:
        raise ValueError

    iou_loss = weight_dict['iou_loss'] * loss_func(pred_mask, gt_mask)
    total_loss += iou_loss
    loss_dict['iou_loss'] = iou_loss.item()

    mask_feature = torch.mean(mask_feature, dim=1, keepdim=True)
    mask_feature = F.interpolate(
        mask_feature, gt_mask.shape[-2:], mode='bilinear', align_corners=False)
    mix_loss = weight_dict['mix_loss']*loss_func(mask_feature, gt_mask)
    total_loss += mix_loss
    loss_dict['mix_loss'] = mix_loss.item()

    if 'temporal_consistency_loss' in weight_dict and weight_dict['temporal_consistency_loss'] > 0:
        batch_size = kwargs.get('batch_size', None)
        frame_num = kwargs.get('frame_num', None)
        alpha = kwargs.get('consistency_alpha', 5.0)
        if batch_size is None or frame_num is None:
            raise ValueError(
                'batch_size and frame_num are required for temporal consistency loss')
        temporal_loss = weight_dict['temporal_consistency_loss'] * AdaptiveTemporalConsistencyLoss(
            pred_mask, gt_mask, batch_size=batch_size, frame_num=frame_num, alpha=alpha)
        total_loss += temporal_loss
        loss_dict['temporal_consistency_loss'] = temporal_loss.item()

    return total_loss, loss_dict
