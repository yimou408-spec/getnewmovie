# 素材来源

## 可选 TMDB 来源（2026-10-31）

`web/app/public/tmdb-logo.svg` 原样取自 [TMDB 官方 API 文档使用的标识](https://files.readme.io/29c6fee-blue_short.svg)，未修改颜色、比例或图形，仅在使用 TMDB 时的关于页小幅展示。页面保留官方免责声明，参见 [署名要求](https://developer.themoviedb.org/docs/faq)。海报使用 API 返回的 poster_path 组成 `https://image.tmdb.org/t/p/w500/…`，不下载到仓库，并链接对应资料页。版权属于相应权利人；离线测试不代表真实 token 验收。

| 文件 | 作者与原始页面 | 许可证 | 使用方式 |
| --- | --- | --- | --- |
| `web/app/public/images/coastal-train.webp` | [Shawn Rain / Unsplash](https://unsplash.com/photos/a-view-of-the-ocean-from-inside-a-train-JCqY2Ji5gj4) | [Unsplash License](https://unsplash.com/license)，2026-10-19 核对：允许免费商业使用、复制、修改与分发 | 首页氛围摄影，2200×1237 WebP，151392 字节；页面保留作者与来源链接 |

图片从原始页面公开的 Unsplash 图片地址取得，转为 WebP 并按容器裁切，叠加文字可读性渐变。它不是项目原创图片，也不是任何候选电影的海报、剧照或观看渠道证据。不作为独立素材售卖或图库内容分发。

Lucide 图标沿用项目依赖 `lucide-react`，许可证为 ISC。品牌文字、排版及页面布局由项目代码实现；没有复制参考网站的品牌或素材。


## 真实电影海报与商店标识（2026-10-19）

海报由 Apple 美国区电影 RSS/lookup 原样返回的 HTTPS `*.mzstatic.com` URL 加载，不下载至仓库，不猜测更大分辨率 URL；仅用于介绍对应影片，并紧邻可点击的对应美国区电影商店链接。API 文档：[Search API](https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/)。

`web/app/public/itunes-store-badge.svg` 是 Apple 官方原始 SVG，未修改图形。来源：[官方标识指南](https://marketing.services.apple/itunes-identity-guidelines)，[官方 US/UK 素材包](https://www.apple.com/105/media/us/ipoditunes/itunes/2018/3a5387c5_1ebd_4993_9633_ff7264dc27bf/itunes-store-badges/us_uk.zip)，包内 `US_UK/iTunes_Store_Badge/Get_it_on/SVG/US_UK_iTunes_Store_Get_Badge_RGB_012618.svg`。页面关于说明保留商标归属。电影与海报版权属于相应权利人；使用公开接口不构成任意商业再授权。
