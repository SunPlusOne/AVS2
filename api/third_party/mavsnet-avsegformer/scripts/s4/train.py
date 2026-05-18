import torch
import time
import torch.nn
import os
import random
import numpy as np
from mmcv import Config
import argparse
from utils import pyutils
from utils.loss_util import LossUtil
from utility import mask_iou
from utils.logger import getLogger
from model import build_model
from dataloader import build_dataset
from loss import IouSemanticAwareLoss


def _get_model_for_io(model):
    return model.module if hasattr(model, 'module') else model


def main():
    # Fix seed
    FixSeed = 123
    random.seed(FixSeed)
    np.random.seed(FixSeed)
    torch.manual_seed(FixSeed)
    torch.cuda.manual_seed(FixSeed)
    torch.backends.cudnn.benchmark = True

    # logger
    log_name = time.strftime('%Y%m%d-%H%M%S', time.localtime())
    dir_name = os.path.splitext(os.path.split(args.cfg)[-1])[0]
    if not os.path.exists(args.log_dir):
        os.mkdir(args.log_dir)
    if not os.path.exists(os.path.join(args.log_dir, dir_name)):
        os.mkdir(os.path.join(args.log_dir, dir_name))
    log_file = os.path.join(args.log_dir, dir_name, f'{log_name}.log')
    logger = getLogger(log_file, __name__)
    logger.info(f'Load config from {args.cfg}')
    logger.info(f'AMP enabled: {args.amp}')

    # config
    cfg = Config.fromfile(args.cfg)
    logger.info(cfg.pretty_text)
    checkpoint_dir = os.path.join(args.checkpoint_dir, dir_name)
    os.makedirs(checkpoint_dir, exist_ok=True)

    # model
    model = build_model(**cfg.model)
    if torch.cuda.device_count() > 1:
        model = torch.nn.DataParallel(model).cuda()
    else:
        model = model.cuda()
    model.train()
    logger.info("Total params: %.2fM" % (sum(p.numel()
                for p in model.parameters()) / 1e6))

    # dataset
    train_dataset = build_dataset(**cfg.dataset.train)
    train_dataloader = torch.utils.data.DataLoader(train_dataset,
                                                   batch_size=cfg.dataset.train.batch_size,
                                                   shuffle=True,
                                                   num_workers=cfg.process.num_works,
                                                   pin_memory=True)
    max_step = (len(train_dataset) // cfg.dataset.train.batch_size) * \
        cfg.process.train_epochs
    val_dataset = build_dataset(**cfg.dataset.val)
    val_dataloader = torch.utils.data.DataLoader(val_dataset,
                                                 batch_size=cfg.dataset.val.batch_size,
                                                 shuffle=False,
                                                 num_workers=cfg.process.num_works,
                                                 pin_memory=True)

    # optimizer
    optimizer = pyutils.get_optimizer(model, cfg.optimizer)
    scaler = torch.cuda.amp.GradScaler(enabled=args.amp)
    loss_util = LossUtil(**cfg.loss)
    avg_meter_miou = pyutils.AverageMeter('miou')

    # Train
    start_epoch = 0
    best_epoch = 0
    global_step = 0
    max_miou = 0.0

    if args.resume is not None and os.path.exists(args.resume):
        logger.info(f'Resume from checkpoint: {args.resume}')
        ckpt = torch.load(args.resume, map_location='cpu')
        if isinstance(ckpt, dict) and 'model' in ckpt:
            _get_model_for_io(model).load_state_dict(ckpt['model'])
            if 'optimizer' in ckpt:
                try:
                    optimizer.load_state_dict(ckpt['optimizer'])
                except RuntimeError as e:
                    if 'out of memory' in str(e).lower():
                        logger.info('Skip optimizer state restore due to CUDA OOM during resume; continue with model weights only.')
                        torch.cuda.empty_cache()
                    else:
                        raise
            start_epoch = ckpt.get('epoch', -1) + 1
            global_step = ckpt.get('global_step', 0)
            max_miou = ckpt.get('max_miou', 0.0)
            best_epoch = ckpt.get('best_epoch', 0)
        else:
            _get_model_for_io(model).load_state_dict(ckpt)
            logger.info('Loaded model weights only (no optimizer/epoch state found).')
        logger.info(
            f"Resumed at epoch={start_epoch}, global_step={global_step}, max_miou={max_miou}")

    for epoch in range(start_epoch, cfg.process.train_epochs):
        if epoch == cfg.process.freeze_epochs:
            if hasattr(model, 'module'):
                model.module.freeze_backbone(False)
            else:
                model.freeze_backbone(False)

        for n_iter, batch_data in enumerate(train_dataloader):
            # [bs, 5, 3, 224, 224], [bs, 5, 1, 96, 64], [bs, 1, 1, 224, 224]
            imgs, audio, mask = batch_data

            imgs = imgs.cuda()
            audio = audio.cuda()
            mask = mask.cuda()
            B, frame, C, H, W = imgs.shape
            imgs = imgs.view(B * frame, C, H, W)
            mask = mask.view(B, H, W)
            audio = audio.view(-1, audio.shape[2],
                               audio.shape[3], audio.shape[4])

            with torch.cuda.amp.autocast(enabled=args.amp):
                output, mask_feature = model(audio, imgs)  # [bs*5, 1, 224, 224]
                loss, loss_dict = IouSemanticAwareLoss(
                    output, mask_feature, mask.unsqueeze(1).unsqueeze(1), **cfg.loss)
            loss_util.add_loss(loss, loss_dict)
            optimizer.zero_grad()
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()

            global_step += 1

            if (global_step - 1) % 50 == 0:
                train_log = 'Iter:%5d/%5d, %slr: %.6f' % (
                    global_step - 1, max_step, loss_util.pretty_out(), optimizer.param_groups[0]['lr'])
                logger.info(train_log)

        # Validation:
        model.eval()
        with torch.no_grad():
            for n_iter, batch_data in enumerate(val_dataloader):
                # [bs, 5, 3, 224, 224], [bs, 5, 1, 96, 64], [bs, 5, 1, 224, 224]
                imgs, audio, mask, _, _ = batch_data

                imgs = imgs.cuda()
                audio = audio.cuda()
                mask = mask.cuda()
                B, frame, C, H, W = imgs.shape
                imgs = imgs.view(B * frame, C, H, W)
                mask = mask.view(B * frame, H, W)
                audio = audio.view(-1, audio.shape[2],
                                   audio.shape[3], audio.shape[4])

                with torch.cuda.amp.autocast(enabled=args.amp):
                    output, _ = model(audio, imgs)

                miou = mask_iou(output.squeeze(1), mask)
                avg_meter_miou.add({'miou': miou})

            miou = (avg_meter_miou.pop('miou'))
            if miou > max_miou:
                model_save_path = os.path.join(
                    checkpoint_dir, '%s_best.pth' % (args.session_name))
                torch.save(_get_model_for_io(model).state_dict(), model_save_path)
                best_epoch = epoch
                logger.info('save best model to %s' % model_save_path)

            max_miou = max(max_miou, miou)

            val_log = 'Epoch: {}, Miou: {}, maxMiou: {}'.format(
                epoch, miou, max_miou)
            # print(val_log)
            logger.info(val_log)

            latest_path = os.path.join(checkpoint_dir, '%s_latest.pth' % (args.session_name))
            torch.save({
                'model': _get_model_for_io(model).state_dict(),
                'optimizer': optimizer.state_dict(),
                'epoch': epoch,
                'global_step': global_step,
                'max_miou': max_miou,
                'best_epoch': best_epoch,
            }, latest_path)
            logger.info('save latest checkpoint to %s' % latest_path)

        model.train()

    logger.info('best val Miou {} at peoch: {}'.format(max_miou, best_epoch))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('cfg', type=str, help='config file path')
    parser.add_argument('--log_dir', type=str,
                        default='work_dir', help='log dir')
    parser.add_argument('--checkpoint_dir', type=str,
                        default='work_dir', help='dir to save checkpoints')
    parser.add_argument("--session_name", default="S4",
                        type=str, help="the S4 setting")
    parser.add_argument('--resume', type=str, default=None,
                        help='path to latest checkpoint for resume training')
    parser.add_argument('--amp', action='store_true', default=True,
                        help='enable mixed precision training')
    parser.add_argument('--no-amp', dest='amp', action='store_false',
                        help='disable mixed precision training')

    args = parser.parse_args()
    main()
