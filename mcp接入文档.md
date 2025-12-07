## med_rag的mcp客户端配置

基于http协议的mcp服务端

地址：http://192.168.3.133:8686/mcp

## 使用事项

配置结束后，询问关于医学相关问题即可触发工具调用。或者在提问的后面添加“请使用med_rag进行回答”进行强制触发工具调用。

## CherryStudio配置

```
{
  "mcpServers": {
    "tUjaQKWFheeLSQebeoQgi": {
      "name": "med_rag",
      "type": "streamableHttp",
      "description": "",
      "isActive": true,
      "timeout": "60",
      "tags": [],
      "baseUrl": "http://192.168.3.133:8686/mcp"
    }
  }
}
```

## roo code配置

```
{
    "mcpServers": {
        "med_rag": {
            "url": "http://192.168.3.133:8686/mcp",
            "type": "streamable-http"
        }
    }
}
```
