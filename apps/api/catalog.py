"""Concept SKUs and proposed retail prices from the product brief."""

PRODUCTS = []
for sku, name, price, weight, description, positions in [
    (
        "frame",
        "LumiRead 一体镜",
        799,
        None,
        "无屏一体镜，集成作业抓拍、桌面光线与近距感知。",
        [[-0.603, 0.1324, -0.0036], [0.602, 0.131, -0.0054], [0, 0.1008, 0.023]],
    ),
    (
        "clip",
        "LumiRead 夹片",
        499,
        13,
        "夹在原有镜框上沿的智能模块，目标重量约 13 克。",
        [[-0.5074, 0.1991, 0.1186], [-0.3608, 0.1975, 0.1176], [-0.435, 0.1978, 0.1174]],
    ),
]:
    sensors = [
        (
            "camera",
            "作业镜头",
            "朝向纸面的摄像头用于记录作业和题目，供学习助手识别与讲解。",
        ),
        ("light", "光线感知", "观察桌面明暗，提示读写环境变化。"),
        ("distance", "近距感知", "留意持续低头贴近书本的读写习惯。"),
    ]
    PRODUCTS.append(
        {
            "sku": sku,
            "name": name,
            "price_cny": price,
            "weight_g": weight,
            "description": description,
            "model_url": f"/products/{sku}.glb",
            "image_url": f"/products/{sku}.webp",
            "hotspots": [
                {"id": i, "label": label, "description": desc, "position": pos}
                for (i, label, desc), pos in zip(sensors, positions, strict=True)
            ],
        }
    )
