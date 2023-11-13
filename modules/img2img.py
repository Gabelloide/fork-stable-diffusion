import os
from contextlib import closing
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps, ImageFilter, ImageEnhance, UnidentifiedImageError
import gradio as gr

from modules import images as imgutil
from modules.generation_parameters_copypaste import create_override_settings_dict, parse_generation_parameters
from modules.processing import Processed, StableDiffusionProcessingImg2Img, process_images
from modules.shared import opts, state
import modules.shared as shared
import modules.processing as processing
from modules.ui import plaintext_to_html
import modules.scripts


def process_batch(p, input_dir, output_dir, inpaint_mask_dir, args, to_scale=False, scale_by=1.0, use_png_info=False, png_info_props=None, png_info_dir=None):
    output_dir = output_dir.strip()
    processing.fix_seed(p)

    images = list(shared.walk_files(input_dir, allowed_extensions=(".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff")))

    is_inpaint_batch = False
    if inpaint_mask_dir:
        inpaint_masks = shared.listfiles(inpaint_mask_dir)
        is_inpaint_batch = bool(inpaint_masks)

        if is_inpaint_batch:
            print(f"\nInpaint batch is enabled. {len(inpaint_masks)} masks found.")

    print(f"Will process {len(images)} images, creating {p.n_iter * p.batch_size} new images for each.")

    state.job_count = len(images) * p.n_iter

    # extract "default" params to use in case getting png info fails
    prompt = p.prompt
    negative_prompt = p.negative_prompt
    seed = p.seed
    cfg_scale = p.cfg_scale
    sampler_name = p.sampler_name
    steps = p.steps

    for i, image in enumerate(images):
        state.job = f"{i+1} out of {len(images)}"
        if state.skipped:
            state.skipped = False

        if state.interrupted:
            break

        try:
            img = Image.open(image)
        except UnidentifiedImageError as e:
            print(e)
            continue
        # Use the EXIF orientation of photos taken by smartphones.
        img = ImageOps.exif_transpose(img)

        if to_scale:
            p.width = int(img.width * scale_by)
            p.height = int(img.height * scale_by)

        p.init_images = [img] * p.batch_size

        image_path = Path(image)
        if is_inpaint_batch:
            # try to find corresponding mask for an image using simple filename matching
            if len(inpaint_masks) == 1:
                mask_image_path = inpaint_masks[0]
            else:
                # try to find corresponding mask for an image using simple filename matching
                mask_image_dir = Path(inpaint_mask_dir)
                masks_found = list(mask_image_dir.glob(f"{image_path.stem}.*"))

                if len(masks_found) == 0:
                    print(f"Warning: mask is not found for {image_path} in {mask_image_dir}. Skipping it.")
                    continue

                # it should contain only 1 matching mask
                # otherwise user has many masks with the same name but different extensions
                mask_image_path = masks_found[0]

            mask_image = Image.open(mask_image_path)
            p.image_mask = mask_image

        if use_png_info:
            try:
                info_img = img
                if png_info_dir:
                    info_img_path = os.path.join(png_info_dir, os.path.basename(image))
                    info_img = Image.open(info_img_path)
                geninfo, _ = imgutil.read_info_from_image(info_img)
                parsed_parameters = parse_generation_parameters(geninfo)
                parsed_parameters = {k: v for k, v in parsed_parameters.items() if k in (png_info_props or {})}
            except Exception:
                parsed_parameters = {}

            p.prompt = prompt + (" " + parsed_parameters["Prompt"] if "Prompt" in parsed_parameters else "")
            p.negative_prompt = negative_prompt + (" " + parsed_parameters["Negative prompt"] if "Negative prompt" in parsed_parameters else "")
            p.seed = int(parsed_parameters.get("Seed", seed))
            p.cfg_scale = float(parsed_parameters.get("CFG scale", cfg_scale))
            p.sampler_name = parsed_parameters.get("Sampler", sampler_name)
            p.steps = int(parsed_parameters.get("Steps", steps))

        proc = modules.scripts.scripts_img2img.run(p, *args)
        if proc is None:
            if output_dir:
                p.outpath_samples = output_dir
                p.override_settings['save_to_dirs'] = False
                if p.n_iter > 1 or p.batch_size > 1:
                    p.override_settings['samples_filename_pattern'] = f'{image_path.stem}-[generation_number]'
                else:
                    p.override_settings['samples_filename_pattern'] = f'{image_path.stem}'
            process_images(p)


def img2img(id_task: str, mode: int, prompt: str, negative_prompt: str, prompt_styles, init_img, sketch, init_img_with_mask, inpaint_color_sketch, inpaint_color_sketch_orig, init_img_inpaint, init_mask_inpaint, steps: int, sampler_name: str, mask_blur: int, mask_alpha: float, inpainting_fill: int, n_iter: int, batch_size: int, cfg_scale: float, image_cfg_scale: float, denoising_strength: float, selected_scale_tab: int, height: int, width: int, scale_by: float, resize_mode: int, inpaint_full_res: bool, inpaint_full_res_padding: int, inpainting_mask_invert: int, img2img_batch_input_dir: str, img2img_batch_output_dir: str, img2img_batch_inpaint_mask_dir: str, override_settings_texts, img2img_batch_use_png_info: bool, img2img_batch_png_info_props: list, img2img_batch_png_info_dir: str, request: gr.Request, *args):

    if len(opts.outdir_samples) != 0: # If not empty
        opts.outdir_samples =  "\\".join(opts.outdir_samples.rsplit("\\", 1)[:-1]) # Cutting [user]
        opts.outdir_samples += f"\\{request.username}" # Adding new username
    else:
        last = opts.outdir_img2img_samples.split("\\")[-1]
        opts.outdir_img2img_samples = "\\".join(opts.outdir_img2img_samples.rsplit("\\")[:-2]) # Cutting last two parts
        opts.outdir_img2img_samples += f"\\{request.username}" # Adding new username
        opts.outdir_img2img_samples += f"\\{last}" # Adding last folder

    if len(opts.outdir_grids) != 0: # If not empty
        opts.outdir_grids = "\\".join(opts.outdir_grids.rsplit("\\", 1)[:-1])
        opts.outdir_grids += f"\\{request.username}"
    else:
        last = opts.outdir_img2img_grids.split("\\")[-1]
        opts.outdir_img2img_grids = "\\".join(opts.outdir_img2img_grids.rsplit("\\")[:-2])
        opts.outdir_img2img_grids += f"\\{request.username}" # Adding new username
        opts.outdir_img2img_grids += f"\\{last}" # Adding last folder

    # Also updating outdir_init_images because img2img might need it if opts.save_init_img == True
    if len(opts.outdir_init_images) != 0: # If not empty
        opts.outdir_init_images =  "\\".join(opts.outdir_init_images.rsplit("\\")[:-2]) # Cutting init-images & [user]
        opts.outdir_init_images += f"\\{request.username}" # Adding new username

    override_settings = create_override_settings_dict(override_settings_texts)

    is_batch = mode == 5

    if mode == 0:  # img2img
        image = init_img
        mask = None
    elif mode == 1:  # img2img sketch
        image = sketch
        mask = None
    elif mode == 2:  # inpaint
        image, mask = init_img_with_mask["image"], init_img_with_mask["mask"]
        mask = processing.create_binary_mask(mask)
    elif mode == 3:  # inpaint sketch
        image = inpaint_color_sketch
        orig = inpaint_color_sketch_orig or inpaint_color_sketch
        pred = np.any(np.array(image) != np.array(orig), axis=-1)
        mask = Image.fromarray(pred.astype(np.uint8) * 255, "L")
        mask = ImageEnhance.Brightness(mask).enhance(1 - mask_alpha / 100)
        blur = ImageFilter.GaussianBlur(mask_blur)
        image = Image.composite(image.filter(blur), orig, mask.filter(blur))
    elif mode == 4:  # inpaint upload mask
        image = init_img_inpaint
        mask = init_mask_inpaint
    else:
        image = None
        mask = None

    # Use the EXIF orientation of photos taken by smartphones.
    if image is not None:
        image = ImageOps.exif_transpose(image)

    if selected_scale_tab == 1 and not is_batch:
        assert image, "Can't scale by because no image is selected"

        width = int(image.width * scale_by)
        height = int(image.height * scale_by)

    assert 0. <= denoising_strength <= 1., 'can only work with strength in [0.0, 1.0]'

    p = StableDiffusionProcessingImg2Img(
        sd_model=shared.sd_model,
        outpath_samples=opts.outdir_samples or opts.outdir_img2img_samples,
        outpath_grids=opts.outdir_grids or opts.outdir_img2img_grids,
        prompt=prompt,
        negative_prompt=negative_prompt,
        styles=prompt_styles,
        sampler_name=sampler_name,
        batch_size=batch_size,
        n_iter=n_iter,
        steps=steps,
        cfg_scale=cfg_scale,
        width=width,
        height=height,
        init_images=[image],
        mask=mask,
        mask_blur=mask_blur,
        inpainting_fill=inpainting_fill,
        resize_mode=resize_mode,
        denoising_strength=denoising_strength,
        image_cfg_scale=image_cfg_scale,
        inpaint_full_res=inpaint_full_res,
        inpaint_full_res_padding=inpaint_full_res_padding,
        inpainting_mask_invert=inpainting_mask_invert,
        override_settings=override_settings,
    )

    p.scripts = modules.scripts.scripts_img2img
    p.script_args = args

    p.user = request.username

    if shared.cmd_opts.enable_console_prompts:
        print(f"\nimg2img: {prompt}", file=shared.progress_print_out)

    if mask:
        p.extra_generation_params["Mask blur"] = mask_blur

    with closing(p):
        if is_batch:
            assert not shared.cmd_opts.hide_ui_dir_config, "Launched with --hide-ui-dir-config, batch img2img disabled"

            process_batch(p, img2img_batch_input_dir, img2img_batch_output_dir, img2img_batch_inpaint_mask_dir, args, to_scale=selected_scale_tab == 1, scale_by=scale_by, use_png_info=img2img_batch_use_png_info, png_info_props=img2img_batch_png_info_props, png_info_dir=img2img_batch_png_info_dir)

            processed = Processed(p, [], p.seed, "")
        else:
            processed = modules.scripts.scripts_img2img.run(p, *args)
            if processed is None:
                processed = process_images(p)

    shared.total_tqdm.clear()

    generation_info_js = processed.js()
    if opts.samples_log_stdout:
        print(generation_info_js)

    if opts.do_not_show_images:
        processed.images = []

    return processed.images, generation_info_js, plaintext_to_html(processed.info), plaintext_to_html(processed.comments, classname="comments")
