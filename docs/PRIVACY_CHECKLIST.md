# 隐私合规检查清单（任务 1.3.2 第 4 条）

> 对照任务书五项逐条勾选，"依据"一栏写明证据（截图/链接/说明），报告第 7 条直接附本清单。

| # | 检查项 | 结论 | 依据 |
|---|---|---|---|
| 1 | 数据来源是否具备合法授权 | ☑ 通过 | SportsMOT 来自官方作者组公开的 HuggingFace 仓库（MCG-NJU/SportsMOT，CC BY-NC 4.0，非门控），课程非商业使用符合许可；结构化数据来自 Kaggle 公开数据集 nathanlauga/nba-games（数据源自 NBA.com 官方统计），遵守其使用条款；引用依据《网络数据安全管理条例》 |
| 2 | 是否遵守目标平台 robots.txt 与 AI 训练数据使用声明 | ☑ 通过 | 爬虫内置 robots.txt 检查（crawl_basketball_news.py 的 robots_allows()），逐 URL 判定。实际核查记录（2026-10-04）：① sports.sina.com.cn robots.txt 为空（200 无规则）= 允许，文章同域；② news.zhibo8.com robots.txt 404 = 按惯例视为允许；③ www.163.com robots.txt 403，Python RobotFileParser 保守判为全部禁止，已弃用网易文章（体现从紧原则）；请求间隔 2s、UA 标识课程机器人、正文仅取 h1-h3/p/li |
| 3 | 合成数据是否符合监管要求 | ☐ 不涉及 | 本实验未使用合成数据（选做项未选） |
| 4 | 是否涉及个人信息；如涉及是否完成匿名化/合成替代 | ☐ 通过 | 赛事转播画面为公开场景，球员为公众人物职业行为，非敏感个人信息；图像 EXIF 元数据已清除（clean_images.py strip_exif()）；结构化数据不含联系方式等私人信息 |
| 5 | 数据使用协议是否满足课程作业授权范围 | ☐ 通过 | 全部数据仅用于本课程作业与非商业研究，不再分发原始数据 |

## 相关法规参考（任务书"重点关注"第 3 条）
- 《网络数据安全管理条例》：https://www.gov.cn/zhengce/zhengceku/202409/content_6977767.htm
- 《个人信息保护合规审计管理办法》：https://www.cac.gov.cn/2025-02/14/c_1741233507681519.htm
- EU AI Act Article 50（AI 生成内容透明度）：本数据集不含 AI 生成内容，不适用
