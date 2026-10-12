# R6A — F-055
初判 FAIL。属实：pages 13 文件、`PAGE_BUILDERS` 12 键（:221-237）、index.html :11-16/:198/:199/:127/:169、api.js 绝大多数、motion/scope-bar/tokens/capabilities 抽查全对、detection.js 文件在未注册。
判错项（已改）：
1. 最危险的一条：原写「仍留有 setInterval 只用于 UI 装饰或与发帧无关」—— 实测 `frontend/js/**/*.js` 共 19 处，漏掉的 `scope-bar.js:4132/:4145` 的 `this._timer = setInterval(() => this._tick(), period)` 正是软轮询【发帧】路径（:4146-4148 自证：寄存器页起 Live 就逐 addr 打 `/api/cmd/reg_read`，跟回放帧抢同一条总线），另有 :1436/:4140 的 16ms drain。已重写该条并列全清单，另注明 `api.js:485 setInterval(ms)` 只是 WS 消息方法名。
2. `store.emit("telemetry:sample")` 实 api.js:151（原写 :152）。
3. `buildConsole` 实 console.js:154（原写 :1，那是文件头注释）。
4. tests.js:11 注释讲的是断言退回默认值，不是 await 链写法 → 改为实测「144 处 await sleep」并举 :3167/:3241/:3350 的 while 形式。
复验：39 处行号引用全部可定位。