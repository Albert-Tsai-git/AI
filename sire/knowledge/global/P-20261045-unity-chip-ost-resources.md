**日期**: 2026-10-26
**项目**: D:/code/GAME
**关键词**: Unity原创芯片音乐, AudioDirector MusicCue, Resources AudioClip, PCM WAV, determinisic music generator, AudioImporter meta, 8-bit chiptune

**需求场景 / 现象**: Unity项目已有事件驱动AudioDirector和十个MusicCue，但Resources没有正式曲目；临时运行时音符生成能验证接线，却没有各场景可辨识的原创主题和一套可反复编修的音乐资产。

**根因**（问题类必填）: 不适用；属于原型占位音频升级为首版原创主题曲资源。

**方案 / 架构**: 保留AudioDirector及cue事件路由，使用Resources/Audio/Music/<MusicCue>.wav的同名映射替换占位回退。用标准库脚本维护手写音符段落，以pulse/triangle/noise合成单声道PCM WAV；七首32小节循环曲使用A/B/主题返回，胜利/失败/住宿使用短非循环段落。静态核对主题描述必须与代码实际使用的噪声、和弦和终止音一致。为生成的Unity资产以Assets相对路径派生稳定GUID；folder meta生成边界必须从 `UNITY/Assets` 开始，不应从仓库根为Unity Assets外的目录建立`.meta`。

**关键文件与接口**:
- `tools/generate_fc_inspired_ost.py` — Cue旋律、BPM、调式、配器与WAV/meta生成。
- `UNITY/Assets/Resources/Audio/Music/<Cue>.wav` — `AudioDirector.PlayMusic`的Resources名称映射。
- `UNITY/Assets/Scripts/Presentation/Audio/AudioDirector.cs` — 先加载 `Resources.Load<AudioClip>("Audio/Music/" + cue)`，缺失时再走占位合成。
- `UNITY/Assets/Scripts/FC/FcTitleScreen.cs` — 音频未听审时将状态写为“首版/待试听”，避免宣称完成或仍写通用占位。

**实施步骤**:
1. 从枚举导出所有音乐cue，分类循环曲与一次性事件曲。
2. 每个cue手写主题短句、速度、调式、和声和配器，使用八分音符片段拼出A/B段及回归；不抄录商业原曲旋律/录音。
3. 以整小节计样本长度，使用短起音/释音与边界fade控制点击爆音，渲染PCM WAV。
4. 将Resources命名与cue保持逐字一致；Unity meta用稳定GUID并严格限制在Assets导入根内。
5. R6静态核对WAV头、帧数/BPM、资源路由、meta和文案；最终音色、循环缝、平台内存须在授权后的Unity听审验证。

**验证方法**: 本次静态检查十首WAV均为22050Hz、mono、16-bit PCM，名称与10个MusicCue匹配；七首循环曲32小节，三首短曲4/4/8小节；10个AudioImporter meta与GUID唯一且位于Assets内。R6A/B/C独立复核与交叉核验PASS。未运行Unity、构建、播放或测试，不能据此断言最终听感通过。

**踩坑**: R6发现Dungeon文案写了金属噪声但配器未实现、Rest说回主音却以2级旋律/非主音和弦结束；修正实际音符数据比仅改文案可靠。初始meta代码从项目根开始走目录树，会生成 `UNITY.meta` 与 `UNITY/Assets.meta` 这类Assets导入根之外的文件；应从 `UNITY/Assets` 推导folder meta，并保留已有GUID。

**状态**: 原创音乐首版已生成并静态复核；Unity导入与听感验收待授权。
