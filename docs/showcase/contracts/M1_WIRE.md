# M1 wire 对齐补充（API_MINIMUM v1.0，派工前对齐）

以下字段唯一；新增小字段不破坏旧v1。/api为浏览器前缀，Python路由不带。

- GET `/demo/status`: `{schema_version:"demo-status-v1",service_state:"ready"|"resetting"|"degraded",ttl_minutes:20|30,conflict_policy:"wait_only"|"takeover_enabled"}`；不透露占用。
- POST `/demo/login`: `{operation_id,username,password}`；正常200是已激活本人lease，耗时202 `{schema_version:"demo-attempt-v1",operation_id,state:"pending"|"ready",reset_id,claimable:boolean}` 并设置HttpOnly pending cookie。同一已激活cookie复用200，不续期。
- GET `/demo/operations/{attempt_operation_id}`：pending cookie或同lease绑定，返回 `{schema_version:"demo-attempt-v1",operation_id,state:"pending"|"ready"|"failed"|"claimed"|"cancelled",reset_id,claimable,error_code?}`；不签业务cookie。GET `/demo/resets/{id}` 同绑定，返回state/phase/error_code，不必额外请求其它auth。
- POST `/demo/claim`: `{operation_id,attempt_operation_id}`；claim自己的新UUID避免和login的请求digest冲突，绑定pending cookie；200设置active Cookie并返回DemoSession。重复claim同operation可返回同本人session metadata，不能凭UUID重发票据。Cookie丢失不另开lease，给明确错误/等待/owner恢复。
- DemoSession: `{schema_version:"demo-session-v1",state:"active",expires_at,server_now,remaining_seconds,lease_generation,seed_version,can_review:boolean,owner_elevated_until:null|string}`。
- 登录423: `{detail:{code:"occupied",message,remaining_seconds,expires_at,takeover_available,lease_generation}}`；401错误凭据无这些字段。
- takeover: `{operation_id,username,password,owner_password,confirm:true,expected_generation}`；202走同pending/claim协议，200已激活则Session。默认wait_only拒绝。owner授权不等于公开共享者可互踢。
- POST `/demo/owner-authorize`: `{operation_id,owner_password,confirm:true}`，当前active lease+Origin；200 `{can_review:true,owner_elevated_until}`，绑定同lease与generation，最长5min或lease到期；不用owner密码创建事实。
- POST `/demo/logout`: `{operation_id}` 200 `{state:"resetting"|"available",reset_id?}`，撤销cookie/入口，前端显示准备/回登录；不自动申请新lease。
- 所有error返回 `{detail:{code,message}}`，额外字段只对已认证的合法冲突/attempt；401expired/taken_over让UI销毁可编辑状态。
- Dashboard沿用API_MINIMUM，overview加`lease_generation:number|null`/`snapshot_at`/`seed_version:string|null`，可非demo本地模式空。`suggested_questions`项href为同源相对路径，前端只导航预填；不自动发送。charts query固定`metric_key`与`sample_mode`，不得换成metric。

主控负责main/AppShell/ResearchHome/runtime接线；UI与后端只新模块，同名共享字段变更先更新本补充并同步两owner。
