"""HCL-native deterministic graph templates, independent of guest support."""
TEMPLATES = [
    {"key": "single_lan", "description": "One router and an optional access switch", "min_routers": 1, "max_routers": 1},
    {"key": "multi_lan", "description": "Router chain, with one LAN per router", "min_routers": 1, "max_routers": 20},
    {"key": "star", "description": "Router hub and independent spokes", "min_routers": 2, "max_routers": 20},
    {"key": "hub_spoke", "description": "Router hub and independent spokes", "min_routers": 2, "max_routers": 20},
    {"key": "three_router_triangle", "description": "Three routers with redundant paths", "min_routers": 3, "max_routers": 3},
]
