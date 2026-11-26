"""Concept SKUs and proposed retail prices from the product brief."""

PRODUCTS = []
for sku, name, price, weight, description, positions in [
    (
        "frame",
        "LumiRead 一体镜",
        799,
        None,
        "无屏一体镜概念，规划作业抓拍、近距与环境光感知，以及眼动与头动采集。",
        [[-0.603, 0.1324, -0.0036], [0.602, 0.131, -0.0054], [0, 0.1008, 0.023]],
    ),
    (
        "clip",
        "LumiRead 夹片",
        499,
        13,
        "保留原有镜片的测距、测光与作业拍摄模块，目标重量约 13 克。",
        [[-0.5074, 0.1991, 0.1186], [-0.3608, 0.1975, 0.1176], [-0.435, 0.1978, 0.1174]],
    ),
]:
    sensors = [
        (
            "camera",
            "作业镜头",
            "朝向纸面的摄像头用于记录作业和题目，供学习助手识别与讲解。",
        ),
        ("light", "光线感知", "观察佩戴位置的明暗，持续偏暗时提示检查桌面照明。"),
        ("distance", "近距感知", "估计镜框到前方读写目标的距离，留意持续偏近的情况。"),
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
