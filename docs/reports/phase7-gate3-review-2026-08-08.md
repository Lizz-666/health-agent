# Phase 7 Gate 3 Codex 独立审查

## 结论

**PASS。** Gate 3 接受 `codex/phase7-implementation` 上的实现
`6c69f9ee07de732f3adda73cecf4e9591e0252d0`。核心实现提交为
`9b44eaddee678effdb23811c120ade6e568660a1`；CI 暴露的 PostgreSQL 迁移测试
隔离缺陷由后续提交 `6c69f9ee07de732f3adda73cecf4e9591e0252d0` 关闭。最终独立冷审
P0/P1/P2 为零。Gate 3 只接受周复盘与跨域草案/Agent 契约；最终合成 E2E、Android
回放和 Phase 7 退出验收仍属于 Task 4。

## Findings First

### 已关闭 P1

1. 周期安全状态曾只看当前状态，无法证明复盘周期内始终允许提案；现同时记录并校验
   period/current safety，任一 restricted/red-flag 均 fail closed。
2. Agent 同日调整曾沿用普通按钮 surface，削弱确认来源审计；现仅允许
   `agent_confirmation`，Agent 只能先提案再通过独立确认工具应用。

### 已关闭 P2

1. 恢复/回退与进阶条件曾混用疲劳、额外正常 check-in 等信号；现恢复可在安全条件下
   处理疲劳，进阶只接受完整四周所需事实，不因额外正常记录而错误阻断。
2. 跨周顺延曾按源周归属执行事实；现 effective session 按实际目标日期归属，并保留
   source/target identity。
3. 周复盘指纹曾遗漏输入身份；现纳入计划、周期、训练/营养/体态来源和版本化安全身份，
   replay 与 stale 判断可复现。
4. 新 active plan 曾使旧回顾不可读，superseded 来源也可能误报 draft；现历史回顾按自身
   来源读取，origin projection 明确区分 draft/active/superseded/deleted。
5. 后端与 Flutter 对趋势、体态比较、安全码和来源组合的严格性不一致；两端现使用一致的
   fail-closed 组合校验，未知枚举、缺失身份和非法结构均进入 parse/unavailable。
6. 营养复盘曾偏离 Phase 6 权威 preparation/pins/fingerprint；现复用既有营养契约，体重
   趋势仅展示，不参与训练决策，长期训练/营养变化只生成草案且不激活。
7. 体态身份最初只覆盖单周，dismissal 可能隐藏后续新比较；现聚合全周期 identity，按
   用户时区记录结构化快照，dismissal 仅抑制对应提醒，不吞掉后续比较或安全信息。
8. 跨域删除与 Agent confirm 幂等引用清理不完整；现用户域删除覆盖 Phase 7 rows 和确认
   引用，不保留可回放的孤立健康上下文。
9. PostgreSQL `0011` 回滚测试在共享数据库中只恢复到 `0011`，使后续 `0012` ORM 测试
   缺列。失败 CI run `31266157082` 将其暴露；测试现先验证 `0011` 边界，再恢复到
   `head`，严格 CI 重跑通过。

## 接受范围与安全边界

- 周复盘快照不可变、可 replay、按输入指纹版本化；真正缺失的数据不会被转成零。
- 训练/营养提案只生成 draft，不能自动激活；进阶要求完整四周门槛，恢复/回退仍受最新
  确定性安全门控制。
- 体重趋势仅展示；体态提醒是应用内周期状态，不引入调度或系统通知，也不能隐藏安全
  状态。
- Agent 仅获得 2 个只读和 5 个提案/确认窄工具；参数不接受策略、日期或安全身份注入，
  所有写入保持所有权、同意、幂等和独立确认边界。
- `0012_review_draft_origins` 只增加 nullable origin FK/index，删除 review 时
  `ON DELETE SET NULL`；downgrade 仅移除新增索引、外键和列，不删除草案或 `0011` 表。
- 没有 live AI、真实健康数据、照片、生产凭据、部署、merge 或 `main` 写入。

## 本地验证

最终接受 SHA `6c69f9ee07de732f3adda73cecf4e9591e0252d0`：

```text
python scripts/verify.py full
PASS: ruff clean; 1617 passed / 0 failed / 38 conditional skipped;
      checked_out_sha=6c69f9ee07de732f3adda73cecf4e9591e0252d0;
      git candidate diff clean

flutter analyze
PASS: No issues found

flutter test
PASS: 472 passed / 0 failed

python -m pytest -q tests/test_training_adaptive_migrations.py \
  tests/test_review_origin_migration.py
PASS: 4 passed / 3 conditional PostgreSQL skips
```

本机没有可用 `PG_TEST_DSN`/PostgreSQL 服务，Docker Desktop 启动也被系统拒绝；因此
本地 38 个条件跳过没有改写为 PostgreSQL 通过。真实 PostgreSQL 16、upgrade/downgrade、
索引、FK 和 `SET NULL` 证据由下述严格 CI 提供。

## Exact-SHA CI

第一次严格 run `31266157082` 在核心实现 SHA `9b44ead` 上失败：`1653 passed / 2 failed`，
根因是既有 `0011` 回滚测试污染共享 schema。修复后 workflow-dispatch run
`31267141017` 的 event SHA 与 checked-out SHA 均为
`6c69f9ee07de732f3adda73cecf4e9591e0252d0`：

```text
Fast:    success; ruff clean; SQLite suite and candidate diff clean
Flutter: success; analyze clean; 472 passed / 0 failed
Full:    success; ruff clean; 1655 passed / 0 failed / 0 skipped;
         PostgreSQL expected=27 / actual=27 / version evidence present
```

`ci-full-summary` 明确记录 `VERIFY_REQUIRE_PG=1`、exact checked-out SHA 和
`OVERALL: PASS`；`ci-fast-summary`、`ci-flutter-summary` 同时存在，三个 job 均成功。

## 残余风险与下一 Gate

没有未解决 P0/P1/P2。P3/运营残余是本地环境不能独立启动 PostgreSQL，已由 exact-SHA
严格 CI 补足而非豁免。Task 4 必须从本 Gate 接受 SHA 开始，直接完成跨端合成 E2E、
Android enabled/disabled 回放、最终冷审、严格 Full/PostgreSQL、exact-SHA CI 和退出审计；
任何实质代码变更都会使本 Gate 测试证据失效并要求新 SHA 重新验证。
