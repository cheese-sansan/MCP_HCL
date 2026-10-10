"""HCL-native deterministic graph templates, independent of guest support."""

TEMPLATES = [
    {
        "key": "single_lan",
        "description": "One router and an optional access switch",
        "min_routers": 1,
        "max_routers": 1,
    },
    {
        "key": "multi_lan",
        "description": "Router chain, with one LAN per router",
        "min_routers": 1,
        "max_routers": 20,
    },
    {
        "key": "star",
        "description": "One router connected to multiple access switches",
        "min_routers": 1,
        "max_routers": 1,
    },
    {
        "key": "hub_spoke",
        "description": "Router hub and independent spokes",
        "min_routers": 2,
        "max_routers": 20,
    },
    {
        "key": "three_router_triangle",
        "description": "Three routers with redundant paths",
        "min_routers": 3,
        "max_routers": 3,
    },
    {
        "key": "multi_lan_wan",
        "description": "Router chain with an explicitly selected WAN provider",
        "min_routers": 1,
        "max_routers": 20,
    },
    {
        "key": "branch_office",
        "description": "Headquarters and branches connected through an explicit WAN provider",
        "min_routers": 2,
        "max_routers": 20,
    },
    {
        "key": "router_on_a_stick",
        "description": "One router and a VLAN trunk with 802.1Q subinterfaces",
        "min_routers": 1,
        "max_routers": 1,
    },
    {
        "key": "custom",
        "description": "Explicit topology plan, with user addressing and service intent preserved",
        "min_routers": 1,
        "max_routers": 20,
    },
]
