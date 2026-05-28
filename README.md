# streetviewFetcher

`streetviewFetcher` 是一个面向中国大陆街景静态图采集流程的 Python 3.11+ 工具。它只封装官方地图服务 API，用于任务规划、坐标转换、图片下载、断点续跑、metadata 存储和本地结果浏览。

项目使用CLI，同时做了streamlit的UI，根目录启动终端即可使用CLI，输入`cnsv ui`进入streamlitUI；项目适用于中国大陆地区的街景爬取，提供了百度和腾讯两个渠道。

转载需注明来源。

项目提供：

- Python 包：`streetviewFetcher`
- CLI 入口：`cnsv`
- Streamlit UI 入口：`cnsv ui` 和 `cnsv-ui`
- CSV、Excel、GeoJSON、bbox、polygon 输入
- 任务计划、坐标系转换、Provider 抽象、并发下载、resume、retry-failed、metadata、结果浏览

## 项目定位

本项目适用于在获得合法权限和授权的前提下，调用官方街景静态图 API 进行研究、内部工具建设或受控数据采集。项目重点是可复现的任务计划、明确的坐标系处理、可断点续跑的下载流程和可审计的 metadata，而不是网页抓取或接口逆向。

## 合规声明

本工具只封装官方 API：

- 百度地图全景静态图 API
- 腾讯位置服务街景相关 API

本项目不支持网页爬虫、逆向接口、抓包复用、私有/内部接口、绕过配额、绕过鉴权，或批量抓取非官方资源。

API 是否可用、是否收费、是否开通、调用配额、商业授权和合规要求，均以百度/腾讯官方控制台、官方文档和服务条款为准。本文档不承诺任何 API 一定免费、默认可用或适合商业用途。

## 安装方式

本地开发安装：

```bash
pip install -e .[dev]
```

查看 CLI：

```bash
cnsv --help
```

## API Key 配置

复制 `.env.example`，或在 shell 中设置环境变量：

```bash
BAIDU_MAP_AK=your_baidu_ak
BAIDU_MAP_SN=your_optional_baidu_sn
TENCENT_MAP_KEY=your_tencent_key
```

CLI 和 UI 会自动加载 `config.yaml` 同目录下的 `.env` 文件；如果同名变量已经在系统环境中存在，系统环境变量优先。

配置文件只保存环境变量名，不保存 Key 原文：

```yaml
baidu:
  ak_env: BAIDU_MAP_AK
  sn_env: BAIDU_MAP_SN
tencent:
  key_env: TENCENT_MAP_KEY
```

Provider debug metadata、CLI 输出、UI 展示和保存的请求参数都会对 Key 做脱敏。

## CLI 使用流程

生成默认配置：

```bash
cnsv init
```

校验配置、输入和 API Key 是否存在：

```bash
cnsv validate --config config.yaml
```

执行本地 Provider 配置检查，不下载图片：

```bash
cnsv validate --config config.yaml --check-api
```

生成任务计划，不下载图片：

```bash
cnsv plan --config config.yaml
```

执行下载：

```bash
cnsv fetch --config config.yaml
```

继续未完成任务：

```bash
cnsv resume --config config.yaml
```

只重试失败任务：

```bash
cnsv retry-failed --config config.yaml
```

查看 metadata 统计：

```bash
cnsv inspect --config config.yaml
```

`dry_run: true` 会阻止图片请求。建议在确认输入、权限、配额和授权之前保持开启。

## UI 使用流程

启动本地 Streamlit UI：

```bash
cnsv ui
# 或
cnsv-ui
```

UI 支持：

- 选择项目目录
- 读取和保存 `config.yaml`
- 上传 CSV、Excel、GeoJSON
- 配置 Provider 和街景参数
- 生成任务计划
- 启动 fetch、resume、retry-failed
- 浏览 metadata 和图片缩略图
- 导出 `tasks.jsonl`、`plan_summary.json`、`metadata.csv`、`errors.csv`

UI 与 CLI 共用 Core Service 层，不会在页面中直接调用百度或腾讯 Provider 私有逻辑。

## 输入格式说明

### 坐标表

CSV 和 Excel 至少支持以下字段：

| 字段 | 是否必填 | 说明 |
|---|---:|---|
| `id` | 否 | 稳定点位 ID。缺失时自动生成。 |
| `lng` | 是 | 经度。 |
| `lat` | 是 | 纬度。 |
| `coord_sys` | 否 | `wgs84`、`gcj02` 或 `bd09`。缺失时使用全局 `coord_sys`。 |
| `provider` | 否 | `baidu`、`tencent`、`both` 或留空。 |
| `panoid` | 否 | 已知街景 pano ID。 |
| `heading` | 否 | 行级 heading 覆盖全局配置。 |
| `pitch` | 否 | 行级 pitch 覆盖全局配置。 |
| `fov` | 否 | 行级 fov 覆盖全局配置。腾讯不支持 fov，只记录 warning。 |
| `tag` | 否 | 用户标签，便于筛选。 |

示例：`examples/input_points.example.csv`。

### bbox 区域采样

配置示例：

```yaml
input_type: bbox
bbox: [116.390, 39.900, 116.400, 39.910]
spacing_meters: 50
coord_sys: wgs84
```

采样器会按 `spacing_meters` 近似生成经纬度网格点。

### GeoJSON 区域采样

配置示例：

```yaml
input_type: geojson
input_path: examples/input_region.example.geojson
spacing_meters: 50
coord_sys: wgs84
```

支持几何类型：

- `Point`
- `MultiPoint`
- `LineString`
- `MultiLineString`
- `Polygon`
- `MultiPolygon`

polygon 采样只保留面内点。

## 配置字段说明

全局字段：

| 字段 | 说明 |
|---|---|
| `provider` | `baidu`、`tencent`、`both` 或 `from_table`。 |
| `input_type` | `table`、`bbox`、`geojson` 或 `polygon`。 |
| `input_path` | table / GeoJSON / polygon 文件输入路径。 |
| `bbox` | `[min_lng, min_lat, max_lng, max_lat]`。 |
| `polygon` | `[lng, lat]` 坐标对列表。 |
| `spacing_meters` | bbox / polygon / line 采样间隔。 |
| `output_dir` | 图片和报告输出目录。 |
| `metadata_path` | metadata 路径，推荐 JSONL。 |
| `coord_sys` | 默认输入坐标系。 |
| `headings` | heading 列表，用于生成笛卡尔积任务。 |
| `pitches` | pitch 列表，用于生成笛卡尔积任务。 |
| `concurrency` | 下载并发数。 |
| `rate_limit` | 近似请求速率限制。 |
| `retry_times` | 通用重试配置；Provider 也有自己的 `max_retries`。 |
| `resume` | fetch 时跳过已成功任务。 |
| `dry_run` | 只计划，不请求图片。 |
| `dedupe` | 按稳定 `task_id` 去重。 |
| `log_level` | 日志级别。 |

百度字段：

| 字段 | 说明 |
|---|---|
| `ak_env` | 百度 AK 环境变量名。 |
| `sn_env` | 百度 SN 环境变量名，可选。 |
| `width`、`height` | 图片尺寸。当前校验：`width <= 1024`、`height <= 512`。 |
| `fov` | 水平视场角。 |
| `coordtype` | `wgs84ll` 或 `bd09ll`。 |
| `use_panoid` | 有 `panoid` 时优先用 panoid 请求。 |
| `timeout` | HTTP 超时时间，单位秒。 |
| `max_retries` | 网络错误重试次数。 |

腾讯字段：

| 字段 | 说明 |
|---|---|
| `key_env` | 腾讯 Key 环境变量名。 |
| `size` | 图片尺寸，例如 `600x480`，最大 `960x640`。 |
| `radius` | `getpano` 搜索半径，最大 `200`。 |
| `use_pano_cache` | 预留 pano 缓存开关。 |
| `skip_no_pano` | 预留 no_pano 跳过行为。 |
| `timeout` | HTTP 超时时间，单位秒。 |
| `max_retries` | 网络错误重试次数。 |

UI 字段：

| 字段 | 说明 |
|---|---|
| `project_dir` | 默认项目目录。 |
| `preview_rows` | 输入预览行数。 |
| `max_preview_points` | UI 中最多预览的点位/任务数量。 |
| `enable_map_preview` | 预留地图预览开关。 |
| `theme` | UI 主题提示。 |
| `auto_refresh_seconds` | 预留自动刷新间隔。 |

## 百度和腾讯 API 差异

| 项目 | 百度 | 腾讯 |
|---|---|---|
| 图片接口 | `https://api.map.baidu.com/panorama/v2` | `https://apis.map.qq.com/ws/streetview/v1/image` |
| Key 参数 | `ak` | `key` |
| 坐标请求 | `location=lng,lat` | `location=lat,lng` |
| pano 请求 | `panoid` | `pano` |
| pano 查询 | 图片接口可用 location 或 panoid | 推荐 `getpano -> image` 两步 |
| 请求坐标系 | 由 `coordtype` 决定 | 默认 GCJ-02 |
| fov | 支持 | 不支持，只 warning |
| 尺寸约束 | 本工具校验最大 1024x512 | 本工具校验最大 960x640 |

## 坐标系说明

支持输入坐标系：

- `wgs84`
- `gcj02`
- `bd09`

Provider 请求坐标系：

- 腾讯默认使用 GCJ-02。
- 百度由 `baidu.coordtype` 决定：
  - `wgs84ll` -> WGS84
  - `bd09ll` -> BD-09

任务中会同时保存原始坐标和请求坐标：

- `source_lng`、`source_lat`、`source_coord_sys`
- `request_lng`、`request_lat`、`request_coord_sys`

如果转换路径不可靠，例如在中国大陆偏移覆盖范围外进行 WGS84 偏移转换，程序会抛出明确异常，而不是静默生成错误坐标。

## metadata 字段说明

metadata 优先使用 JSONL，便于追加和断点续跑。

常见字段：

| 字段 | 说明 |
|---|---|
| `task_id` | 稳定任务 ID。 |
| `provider` | `baidu` 或 `tencent`。 |
| `point_id` | 输入点位 ID。 |
| `source_*` | 原始坐标字段。 |
| `request_*` | Provider 请求坐标字段。 |
| `heading`、`pitch`、`fov` | 视角参数。 |
| `status` | `success`、`failed`、`no_pano` 或 `skipped`。 |
| `image_path` | 成功保存的图片路径。 |
| `image_md5` | 图片 MD5。 |
| `image_size_bytes` | 图片大小。 |
| `error_type`、`error_code`、`error_message` | 错误分类。 |
| `provider_metadata` | 已脱敏的 Provider 元数据。 |
| `debug_info` | 已脱敏的调试信息。 |
| `completed_at` | 完成时间。 |

metadata 不保存 API Key 原文。

## 常见错误说明

| 错误 | 常见原因 | 处理建议 |
|---|---|---|
| Missing API key env var | 环境变量未设置 | 设置 `BAIDU_MAP_AK` 或 `TENCENT_MAP_KEY`，或修改配置中的环境变量名。 |
| Invalid coordinate | 经纬度超出范围 | 检查输入列和坐标顺序。 |
| Unsupported coord_sys | 坐标系拼写错误或不支持 | 使用 `wgs84`、`gcj02` 或 `bd09`。 |
| Tencent size too large | `size` 超过 `960x640` | 调小 `tencent.size`。 |
| Tencent radius too large | `radius > 200` | 调小 `tencent.radius`。 |
| no_pano | 附近没有街景 | 检查坐标，或在官方限制内增大腾讯 `radius`。 |
| auth_error | Key 无效、服务未开通、权限或配额问题 | 检查官方控制台的权限、配额、计费和服务开通状态。 |
| param_error | 请求参数被官方接口拒绝 | 检查尺寸、坐标系、坐标顺序、heading、pitch、pano id。 |

## 不支持事项

本项目不支持：

- 网页爬虫
- 逆向接口
- 抓包复用内部接口
- 绕过配额
- 绕过授权
- 批量抓取非官方资源
- 声称官方 API 一定免费或所有账号都可用

请始终遵守官方服务条款和所在地法律法规。

## 示例文件

- `.env.example`
- `examples/config.example.yaml`
- `examples/input_points.example.csv`
- `examples/input_region.example.geojson`

根目录的 `config.yaml` 是 dry-run 起始配置。确认官方权限、配额和授权后，再关闭 `dry_run`。
