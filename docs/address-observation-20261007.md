# IPv6 与重复地址的路由域观察：软件稿，待 DeepSeek 测试

2026-10-07，Asia/Tokyo。同一nat-transactions软件工作区扩展hcl_diff/hcl_health_check，声明53工具/6资源不变。本轮仅做源码、厂商二进制标识和命令文档的静态分析，以及Schema/构建制品；功能、单元、模拟、SDK发现/调用与原生测试均0。

## 输入和查询范围

差异请求包含IPv6计划地址时，仅对相关设备加读 `display ipv6 interface`。健康请求新增严格布尔 `include_ipv6=false`；明确为true时才加读IPv6。其他设备仍保留原IPv4查询范围。IPv4观察发现重复地址后，才为拥有这些地址的设备新建身份绑定连接，读取一次 `display ip interface brief` 的VPN列；不重放配置命令。第二次读取必须仍是原VM UUID及原阶段文件，并核对目标接口主IPv4地址/前缀没有变。

## 命令来源与语义

旧本机详细IPv6语法/示例来自 `D:/HCL/CMD-help/896185720/1748081527/-1100069344.htm`，SHA256 `9db97598a1b8cf14ab7e9ca8e066e05680456326a059a1b87b114dd012c8ea20`。该文档GB2312，静态提取使用GB18030解码。保留全球单播、链路本地、前缀、DAD/来源标记和生命周期。补充语义参考 [H3C IPv6命令](https://www.h3c.com/en/d_202409/2277294_294551_0.htm)：TENTATIVE/DUPLICATE地址不能用于正常报文源/目的；DEPRECATED与preferred生命周期另行记录，不据此证明邻居或连通性。

主地址/辅助地址的IPv4处理不变。IPv6精确比较地址集合与计划：链路本地不替代全球单播；匹配地址处于DAD未可用状态时为不可确认。缺链路本地前缀不猜/64。未知注释、非法地址/子网、重复记录、矛盾使能状态或不完整段落拒绝该次IPv6结果，已经取得的IPv4诊断仍保留。

VPN表格式来源为 [H3C IP接口示例](https://www.h3c.com/en/d_202404/2102309_294551_0.htm)；无VPN列的旧格式保持unknown。仅合并精确接口名和文档中的GE/GigabitEthernet对应；其他缩写不猜。显式`--`按文档表示公共路由域，缺字段不能推断公共域。只给重复IPv4所涉及的接口附加该域，辅助地址沿用同接口的IPv4域；不把此列外推为IPv6域。

健康结果同时保留全部已观察重复IPv4，以及已知同IPv4域的重复分组。不同域合法复用不会列入同域分组。可用全球IPv6的重复诊断排除已标记ANYCAST，链路本地不进入跨接口重复表；DAD未可用/有效生命周期为0的地址另列。IPv6域仍未知，不能以这些观察判定全拓扑健康。

额外查询沿用剩余预算、独占管道、命令回显/提示符/原始哈希校验。原生/模拟、IPv6字段覆盖与阶段绑定覆盖分开；阶段文件中途变化会撤销归因。完整原生设备/线缆库存和原子快照仍缺，healthy/in_sync正向结论、完整行为等价及full_live_gate_passed不提升。

## 原生库存入口的静态调查

本机 `D:/HCL/SimwareWrapper.exe` SHA256 `a8c2654d3441b1e9040b1a1c565e441713676e6a78a3bc99db17eae8ce09705a`。二进制可见70个候选处理标识，包含接口、网关、抓包和生命周期名称；名称并不能确定协议参数或副作用。中性Python3.8格式解析只覆盖bootstrap代码，未得到完整分派合同，不能据此声称完整调查排除了所有库存入口。

本地只读分析记录位于 `work/native-wrapper-contract-20261007/wrapper-inventory-candidates.json` 与 `marshal-metadata.json`；原程序/镜像未修改，没有执行厂商代码或发送原生请求。分析格式依据 [CPython 3.8 marshal定义](https://raw.githubusercontent.com/python/cpython/v3.8.20/Python/marshal.c)，私有分析脚本不进入候选wheel。原生完整库存入口仍未确认，未知动词未开放。

## DeepSeek 必要验项

固定候选/源码哈希，检查include_ipv6严格类型/默认行为、仅相关设备的IPv6读取、主/辅助/链路本地/全球地址及前缀、空段落与disabled、TENTATIVE/DUPLICATE/DEPRECATED/ANYCAST/生命周期、格式冲突及部分读取失败。检查重复IPv4才触发VPN表、旧列缺失、跨/同域、别名歧义、第二次身份/地址变化、超时/管道占用和回执失败，维护53声明的Schema。

这是待验清单，Codex没有执行。旧候选和失败保留，沿用有效范围结果；不重跑无变化的完整回归或旧成功guest启动。账号仍供必要真实测试使用，完成后按创建SID删除并保留数据的条件授权不变。完整61/5复现仍Incomplete，12/46/3计数不提升。
