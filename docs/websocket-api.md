# WebSocket 服务调用文档

## 一、概述

- **技术栈**：Socket.IO（与 HTTP 同端口）
- **连接路径**：`/ws`
- **转发接口**：`POST /api/v1/ws/forward`（需 JWT）
- **默认事件名**：`forward`（可自定义）

服务端收到转发请求后，会将 `payload` 以指定 `event` 广播给**所有已连接的 WebSocket 客户端**。

---

## 二、客户端连接（Socket.IO）

### 2.1 连接地址

| 环境     | 地址示例                    |
|----------|-----------------------------|
| 本地开发 | `http://localhost:3000`     |
| 生产     | `https://your-domain.com`   |

Socket.IO 的 **path** 为 `/ws`，需在客户端选项中指定。

### 2.2 浏览器（JavaScript）

```html
<script src="https://cdn.socket.io/4.x/socket.io.min.js"></script>
<script>
  const socket = io('http://localhost:3000', {
    path: '/ws',
    transports: ['websocket', 'polling'],
  });

  socket.on('connect', () => {
    console.log('已连接:', socket.id);
  });

  // 监听默认转发事件
  socket.on('forward', (data) => {
    console.log('收到转发消息:', data);
  });

  // 若服务端使用了自定义 event，例如 'notification'
  socket.on('notification', (data) => {
    console.log('收到通知:', data);
  });

  socket.on('disconnect', (reason) => {
    console.log('已断开:', reason);
  });
</script>
```

### 2.3 Node.js / 前端项目（npm）

```bash
npm install socket.io-client
```

```javascript
import { io } from 'socket.io-client';

const socket = io('http://localhost:3000', {
  path: '/ws',
  transports: ['websocket', 'polling'],
});

socket.on('connect', () => console.log('已连接:', socket.id));
socket.on('forward', (data) => console.log('收到转发:', data));
socket.on('disconnect', () => console.log('已断开'));
```

### 2.4 微信小程序

需使用支持 Socket.IO 或 WebSocket 的库，连接地址为：`wss://your-domain.com/ws`（或对应 ws 路径），并按照 Socket.IO 握手协议连接。事件监听方式同上（如 `on('forward', callback)`）。

---

## 三、HTTP 转发接口

通过 HTTP 把一条消息广播给所有已连接的 WebSocket 客户端。

### 3.1 接口说明

| 项目     | 说明                          |
|----------|-------------------------------|
| 方法     | `POST`                        |
| 路径     | `/api/v1/ws/forward`          |
| 认证     | Bearer JWT（Header 必填）      |
| Content-Type | `application/json`       |

### 3.2 请求体（ForwardMessageDto）

| 字段     | 类型   | 必填 | 说明 |
|----------|--------|------|------|
| event    | string | 否   | 事件名，客户端用此名监听；不传默认为 `forward` |
| payload  | object | 是   | 要下发的数据，任意 JSON 对象 |

### 3.3 响应

```json
{
  "ok": true,
  "event": "forward"
}
```

- `event` 为实际下发时使用的事件名（与请求体中的 `event` 或默认 `forward` 一致）。

### 3.4 cURL 示例

```bash
# 使用默认事件 "forward"
curl -X POST "http://localhost:3000/api/v1/ws/forward" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{"payload":{"type":"notification","content":"新消息"}}'

# 使用自定义事件 "notification"
curl -X POST "http://localhost:3000/api/v1/ws/forward" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{"event":"notification","payload":{"title":"提示","body":"内容"}}'
```

### 3.5 Axios（JavaScript）

```javascript
const axios = require('axios');

async function forwardMessage(token, payload, event = 'forward') {
  const { data } = await axios.post(
    'http://localhost:3000/api/v1/ws/forward',
    { event, payload },
    {
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
    },
  );
  return data; // { ok: true, event: 'forward' }
}

// 使用
forwardMessage('YOUR_JWT', { type: 'alert', message: 'hello' });
```

### 3.6 Swagger

在项目 Swagger 页面（如 `http://localhost:3000/api`）中，找到 **WebSocket** 分组下的 **POST /api/v1/ws/forward**，可直接在页面上填写 JWT 和请求体进行调试。

---

## 四、服务端内部调用（WsService）

其他 Nest 模块不需要走 HTTP，可直接注入 `WsService` 做转发。

### 4.1 引入模块

在需要调用转发的模块中导入 `WsModule`：

```typescript
// xxx.module.ts
import { Module } from '@nestjs/common';
import { WsModule } from '../ws/ws.module';
import { XxxService } from './xxx.service';

@Module({
  imports: [WsModule],
  providers: [XxxService],
})
export class XxxModule {}
```

### 4.2 注入并调用

```typescript
// xxx.service.ts
import { Injectable } from '@nestjs/common';
import { WsService } from '../ws/ws.service';

@Injectable()
export class XxxService {
  constructor(private readonly wsService: WsService) {}

  doSomething() {
    // 使用默认事件 "forward"
    this.wsService.forward({
      type: 'notification',
      content: '新消息',
    });

    // 指定事件名
    this.wsService.forward(
      { title: '提示', body: '内容' },
      'notification',
    );

    // 使用 DTO 格式（event + payload）
    this.wsService.forwardWithDto({
      event: 'custom-event',
      payload: { key: 'value' },
    });
  }
}
```

### 4.3 API 摘要

| 方法 | 说明 |
|------|------|
| `forward(payload, event?)` | 广播 `payload`，`event` 可选，默认 `'forward'` |
| `forwardWithDto({ event?, payload })` | 按 DTO 格式广播，`event` 可选 |

---

## 五、常见问题

**Q：客户端连不上？**  
确认服务端已启用 Socket.IO 适配器（main.ts 中 `IoAdapter`），且客户端使用的 **path** 为 `/ws`，地址与 HTTP 一致（仅协议可为 ws/wss）。

**Q：收不到转发消息？**  
1. 客户端是否监听了正确的事件名（与请求里的 `event` 或默认 `forward` 一致）。  
2. 转发接口是否返回 200 且 `ok: true`。  
3. 是否在连接成功之后再调用转发接口。

**Q：转发接口 401？**  
请求头需带有效 JWT：`Authorization: Bearer <token>`。

**Q：如何只推给部分客户端？**  
当前实现是广播给所有连接。若要做房间或定向推送，需在网关层维护 socket 与用户/房间的映射，并只对目标 socket 调用 `emit`，可在后续迭代中扩展。

---

## 六、相关文件

- 网关：`src/modules/ws/ws.gateway.ts`
- 服务：`src/modules/ws/ws.service.ts`
- 控制器：`src/modules/ws/ws.controller.ts`
- DTO：`src/modules/ws/dto/forward-message.dto.ts`
