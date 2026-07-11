# iframe 嵌入问数

## 启用

```bash
EMBED_ENABLED=true
EMBED_APP_ID=your-app
EMBED_APP_SECRET=your-secret
EMBED_ALLOWED_ORIGINS=https://portal.example.com
EMBED_TOKEN_TTL_SEC=3600
```

## 签发 Token

**超管**（已登录）：

```http
POST /api/v1/embed/token/admin
Authorization: Bearer <admin-jwt>
Content-Type: application/json

{ "userId": 2, "role": "OPERATOR" }
```

**第三方 appId/secret**：

```http
POST /api/v1/embed/token
Content-Type: application/json

{
  "appId": "your-app",
  "appSecret": "your-secret",
  "userId": 2,
  "role": "SCHOOL"
}
```

响应：`{ "accessToken": "...", "expiresIn": 3600 }`

## iframe 集成

```html
<iframe
  src="https://copilot.example.com/embed/ask?token=ACCESS_TOKEN"
  width="100%"
  height="640"
  style="border:0"
></iframe>
```

## postMessage（可选）

父页面可向 iframe 发送：

```js
iframe.contentWindow.postMessage(
  { type: 'copilot:ask', question: '本月参与人数' },
  'https://copilot.example.com'
)
```

前端需配置 `VITE_EMBED_ORIGINS` 白名单校验来源。

## 安全说明

- embed token 带 `scope=embed`，**无法访问** `/admin/*` 接口
- Token 短 TTL，过期后需重新签发
- 生产环境配置 `EMBED_FRAME_ANCESTORS` 限制可被嵌入的父页面
