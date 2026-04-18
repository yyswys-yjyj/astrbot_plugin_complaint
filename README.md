# 🤖 机器人告状插件 (Complaint Plugin)

<p align="center">
  <img src="https://visitor.serveryyswys.top/cnt/astrbot_plugin_complaint"></img><br>
  <strong>一个当AI在受到用户欺负、侮辱或不公平对待时，能够向管理员告状的AstrBot插件。</strong><br><br>
  <a href="https://opensource.org/licenses/MIT" target="_blank" rel="noopener noreferrer"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="MIT license"></a>
</p>




> 提示：该插件由AI编写，可能存在些许问题

## ✨ 功能特点

- 🗣️ **AI主动告状**：当AI判断自己受到欺负时，自动调用工具向管理员告状
- 📨 **私聊通知**：向所有系统管理员发送私聊消息
- 📝 **详细上下文**：告状消息包含用户信息、群组信息和触发消息
- 🔧 **简单配置**：只需在AstrBot主配置中设置管理员ID，在人格设定里写怎么用该工具

## 📋 支持的平台

 - aiocqhttp

## 🚀 使用方法

### 教会AI怎么用

安装该插件，改个人格设定，例如“当你感到被欺负、调戏、打压或不公平对待时，或是用户向你发送了涉黄内容，请随时向管理员打小报告”

### 配置管理员
#### 1.常规管理员

只需要前往`配置文件 / 平台设置 / 管理员 ID`配置好管理员ID


#### 2.唯一管理员（备用管理员）

在插件配置中进行设置    
要获取完整的UMO，请使用`/sid`指令获取


**请注意**：请勿把WebUI作为管理员账号   

### 测试指令

插件提供了一个指令：`/complaint_test`   
你可以使用该指令测试告状插件是否工作正常   
