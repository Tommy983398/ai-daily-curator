"""
send_email.py - 通过 QQ 邮箱 SMTP 发送 AI 日报

读取 latest.md 文件，转换为 HTML 格式后通过 QQ 邮箱发送。

环境变量:
- QQ_MAIL_AUTH_CODE: QQ 邮箱 SMTP 授权码
- GITHUB_TOKEN: GitHub Token（备用，用于获取日期）
"""

import os
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone
import markdown


def get_smtp_config() -> dict:
    """获取 SMTP 配置"""
    auth_code = os.environ.get("QQ_MAIL_AUTH_CODE", "")
    if not auth_code:
        raise ValueError("未设置 QQ_MAIL_AUTH_CODE 环境变量，无法发送邮件")

    return {
        "smtp_server": "smtp.qq.com",
        "smtp_port": 465,
        "sender": "mincheng_1010@qq.com",
        "receiver": "mincheng_1010@qq.com",
        "auth_code": auth_code,
    }


def md_to_html(md_content: str) -> str:
    """将 Markdown 转换为 HTML 邮件内容"""
    # 使用 markdown 库转换
    html_body = markdown.markdown(
        md_content,
        extensions=["extra", "toc", "nl2br"],
    )

    # 包装成完整的 HTML 邮件模板
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f8f9fa;
        }}
        .container {{
            background-color: #ffffff;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #1a1a2e;
            border-bottom: 3px solid #e94560;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #16213e;
            margin-top: 30px;
            border-left: 4px solid #0f3460;
            padding-left: 12px;
        }}
        h3 {{
            color: #1a1a2e;
        }}
        blockquote {{
            border-left: 4px solid #e94560;
            padding: 8px 16px;
            margin: 10px 0;
            background-color: #fff5f5;
            color: #555;
        }}
        a {{
            color: #0f3460;
            text-decoration: none;
        }}
        a:hover {{
            text-decoration: underline;
        }}
        hr {{
            border: none;
            border-top: 1px solid #e0e0e0;
            margin: 30px 0;
        }}
        ul {{
            padding-left: 20px;
        }}
        li {{
            margin: 5px 0;
        }}
        code {{
            background-color: #f0f0f0;
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 0.9em;
        }}
    </style>
</head>
<body>
    <div class="container">
        {html_body}
    </div>
</body>
</html>"""

    return html


def send_email():
    """发送 AI 日报邮件"""
    config = get_smtp_config()
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # 读取 latest.md
    try:
        with open("latest.md", "r", encoding="utf-8") as f:
            md_content = f.read()
    except FileNotFoundError:
        print("❌ latest.md 文件不存在，请先运行 generate_report.py")
        return False

    # 转换为 HTML
    html_content = md_to_html(md_content)

    # 构建邮件
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"AI 日报 - {date_str}"
    msg["From"] = config["sender"]
    msg["To"] = config["receiver"]

    # 纯文本备用（部分邮件客户端不支持 HTML）
    msg.attach(MIMEText(md_content, "plain", "utf-8"))
    # HTML 正文
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    # 发送邮件
    print(f"[邮件] 正在通过 {config['smtp_server']}:{config['smtp_port']} 发送...")
    print(f"[邮件] 收件人: {config['receiver']}")

    context = ssl.create_default_context()

    try:
        with smtplib.SMTP_SSL(config["smtp_server"], config["smtp_port"], context=context) as server:
            server.login(config["sender"], config["auth_code"])
            server.sendmail(config["sender"], config["receiver"], msg.as_string())
            print("✅ 邮件发送成功！")
            return True
    except smtplib.SMTPAuthenticationError:
        print("❌ SMTP 认证失败：请检查 QQ_MAIL_AUTH_CODE 是否正确")
        return False
    except smtplib.SMTPException as e:
        print(f"❌ SMTP 发送失败: {e}")
        return False
    except Exception as e:
        print(f"❌ 邮件发送异常: {e}")
        return False


if __name__ == "__main__":
    success = send_email()
    exit(0 if success else 1)
