import json
import random
import time
import uuid
import zlib
from .crypto import encrypt

def encode_with_crc(obj):
    payload = json.dumps(obj, separators=(',', ':')).encode('utf-8')
    crc = zlib.crc32(payload) & 0xFFFFFFFF
    hex_crc = f"{crc:08x}"
    checksum = hex_crc.encode('ascii').upper()
    return checksum, checksum + b"#" + payload

# Inline sample GPU data (webgl.json equivalent)
SAMPLE_GPUS = [
    {"webgl": [[{"webgl_unmasked_vendor": "Google Inc.", "webgl_unmasked_renderer": "ANGLE (Intel, Intel(R) UHD Graphics (0x00009BC4) Direct3D11 vs_5_0 ps_5_0, D3D11)", "webgl_extensions": "ANGLE_instanced_arrays;EXT_blend_minmax;EXT_color_buffer_half_float;EXT_disjoint_timer_query;EXT_float_blend;EXT_frag_depth;EXT_shader_texture_lod;EXT_texture_compression_bptc;EXT_texture_compression_rgtc;EXT_texture_filter_anisotropic;EXT_sRGB;KHR_parallel_shader_compile;OES_element_index_uint;OES_fbo_render_mipmap;OES_standard_derivatives;OES_texture_float;OES_texture_float_linear;OES_texture_half_float;OES_texture_half_float_linear;OES_vertex_array_object;WEBGL_color_buffer_float;WEBGL_compressed_texture_s3tc;WEBGL_compressed_texture_s3tc_srgb;WEBGL_debug_renderer_info;WEBGL_debug_shaders;WEBGL_depth_texture;WEBGL_draw_buffers;WEBGL_lose_context;WEBGL_multi_draw"}]], "webgl_unmasked_renderer": "ANGLE (Intel, Intel(R) UHD Graphics (0x00009BC4) Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"webgl": [[{"webgl_unmasked_vendor": "Google Inc.", "webgl_unmasked_renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)", "webgl_extensions": "ANGLE_instanced_arrays;EXT_blend_minmax;EXT_color_buffer_half_float;EXT_disjoint_timer_query;EXT_float_blend;EXT_frag_depth;EXT_shader_texture_lod;EXT_texture_compression_bptc;EXT_texture_compression_rgtc;EXT_texture_filter_anisotropic;EXT_sRGB;KHR_parallel_shader_compile;OES_element_index_uint;OES_fbo_render_mipmap;OES_standard_derivatives;OES_texture_float;OES_texture_float_linear;OES_texture_half_float;OES_texture_half_float_linear;OES_vertex_array_object;WEBGL_color_buffer_float;WEBGL_compressed_texture_s3tc;WEBGL_compressed_texture_s3tc_srgb;WEBGL_debug_renderer_info;WEBGL_debug_shaders;WEBGL_depth_texture;WEBGL_draw_buffers;WEBGL_lose_context;WEBGL_multi_draw"}]], "webgl_unmasked_renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"webgl": [[{"webgl_unmasked_vendor": "Google Inc.", "webgl_unmasked_renderer": "ANGLE (AMD, AMD Radeon(TM) Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)", "webgl_extensions": "ANGLE_instanced_arrays;EXT_blend_minmax;EXT_color_buffer_half_float;EXT_disjoint_timer_query;EXT_float_blend;EXT_frag_depth;EXT_shader_texture_lod;EXT_texture_compression_bptc;EXT_texture_compression_rgtc;EXT_texture_filter_anisotropic;EXT_sRGB;KHR_parallel_shader_compile;OES_element_index_uint;OES_fbo_render_mipmap;OES_standard_derivatives;OES_texture_float;OES_texture_float_linear;OES_texture_half_float;OES_texture_half_float_linear;OES_vertex_array_object;WEBGL_color_buffer_float;WEBGL_compressed_texture_s3tc;WEBGL_compressed_texture_s3tc_srgb;WEBGL_debug_renderer_info;WEBGL_debug_shaders;WEBGL_depth_texture;WEBGL_draw_buffers;WEBGL_lose_context;WEBGL_multi_draw"}]], "webgl_unmasked_renderer": "ANGLE (AMD, AMD Radeon(TM) Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"webgl": [[{"webgl_unmasked_vendor": "Apple", "webgl_unmasked_renderer": "Apple M1", "webgl_extensions": "ANGLE_instanced_arrays;EXT_blend_minmax;EXT_color_buffer_half_float;EXT_disjoint_timer_query;EXT_float_blend;EXT_frag_depth;EXT_shader_texture_lod;EXT_texture_filter_anisotropic;EXT_sRGB;KHR_parallel_shader_compile;OES_element_index_uint;OES_fbo_render_mipmap;OES_standard_derivatives;OES_texture_float;OES_texture_float_linear;OES_texture_half_float;OES_texture_half_float_linear;OES_vertex_array_object;WEBGL_color_buffer_float;WEBGL_debug_renderer_info;WEBGL_debug_shaders;WEBGL_depth_texture;WEBGL_draw_buffers;WEBGL_lose_context;WEBGL_multi_draw"}]], "webgl_unmasked_renderer": "Apple M1"},
]
GPUS = SAMPLE_GPUS

def get_fp(user_agent: str):
    ts = int(time.time() * 1000)
    gpu = random.choice(GPUS)
    bins = [random.randrange(0, 40) for _ in range(256)]
    bins[0], bins[-1] = random.randrange(14473, 16573), random.randrange(14473, 16573)

    fp = {
        "metrics": {"fp2": 1, "browser": 0, "capabilities": 1, "gpu": 7, "dnt": 0, "math": 0, "screen": 0,
                    "navigator": 0, "auto": 1, "stealth": 0, "subtle": 0, "canvas": 5, "formdetector": 1, "be": 0},
        "start": ts,
        "flashVersion": None,
        "plugins": [{"name": "PDF Viewer", "str": "PDF Viewer "},
                    {"name": "Chrome PDF Viewer", "str": "Chrome PDF Viewer "},
                    {"name": "Chromium PDF Viewer", "str": "Chromium PDF Viewer "},
                    {"name": "Microsoft Edge PDF Viewer", "str": "Microsoft Edge PDF Viewer "},
                    {"name": "WebKit built-in PDF", "str": "WebKit built-in PDF "}],
        "dupedPlugins": "PDF Viewer Chrome PDF Viewer Chromium PDF Viewer Microsoft Edge PDF Viewer WebKit built-in PDF ||1920-1080-1032-24-*-*-*",
        "screenInfo": "1920-1080-1032-24-*-*-*",
        "referrer": "",
        "userAgent": user_agent,
        "location": "",
        "webDriver": False,
        "capabilities": {
            "css": {"textShadow": 1, "WebkitTextStroke": 1, "boxShadow": 1, "borderRadius": 1,
                    "borderImage": 1, "opacity": 1, "transform": 1, "transition": 1},
            "js": {"audio": True, "geolocation": random.choice([True, False]),
                   "localStorage": "supported", "touch": False, "video": True,
                   "webWorker": random.choice([True, False])},
            "elapsed": 1
        },
        "gpu": {
            "vendor": gpu["webgl"][0][0]["webgl_unmasked_vendor"],
            "model": gpu["webgl_unmasked_renderer"],
            "extensions": gpu["webgl"][0][0]["webgl_extensions"].split(";")
        },
        "dnt": None,
        "math": {"tan": "-1.4214488238747245", "sin": "0.8178819121159085", "cos": "-0.5753861119575491"},
        "automation": {"wd": {"properties": {"document": [], "window": [], "navigator": []}},
                       "phantom": {"properties": {"window": []}}},
        "stealth": {"t1": 0, "t2": 0, "i": 1, "mte": 0, "mtd": False},
        "crypto": {"crypto": 1, "subtle": 1, "encrypt": True, "decrypt": True,
                   "wrapKey": True, "unwrapKey": True, "sign": True, "verify": True,
                   "digest": True, "deriveBits": True, "deriveKey": True,
                   "getRandomValues": True, "randomUUID": True},
        "canvas": {"hash": random.randrange(645172295, 735192295),
                   "emailHash": None, "histogramBins": bins},
        "formDetected": False, "numForms": 0, "numFormElements": 0,
        "be": {"si": False},
        "end": ts + 1, "errors": [], "version": "2.4.0",
        "id": str(uuid.uuid4()),
    }
    checksum, data = encode_with_crc(fp)
    return checksum.decode(), encrypt(data)
