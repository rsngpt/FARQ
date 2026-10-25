#!/usr/bin/env python3
import sys
import json
import os
from PIL import Image, ImageDraw, ImageFont

def get_font(size, bold=False):
    paths = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf"
    ]
    for p in paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()

def generate_verdict_card(data, output_path):
    width, height = 1200, 675
    verdict = (data.get("verdict") or "NOT_VERIFIED").upper()
    
    if verdict in ["CONFIRMED_SCAM", "LIKELY_SCAM"]:
        bg_color = (13, 17, 28)
        panel_color = (22, 27, 46)
        accent_color = (239, 68, 68)      # Bright Red
        badge_bg = (220, 38, 38)
        badge_text = "🚨 A HUGE SCAM ALERT"
        title_text = "Altered Video Detected"
        sub_text = "The face and the voice in this video were not recorded together."
        bullet_1 = "• Acoustic & visual mismatch: facial movements do not match audio"
        bullet_2 = "• Official source: voice was spliced over archive video footage"
        action_text = "🚨 CALL 1930 NOW TO FREEZE FUNDS · DO NOT PAY"
        action_bg = (185, 28, 28)
    elif verdict in ["SAFE", "GENUINE", "AUTHENTIC"]:
        bg_color = (10, 24, 20)
        panel_color = (16, 37, 30)
        accent_color = (16, 185, 129)     # Emerald Green
        badge_bg = (5, 150, 105)
        badge_text = "🛡️ NO SCAM FOUND"
        title_text = "No Manipulation Detected"
        sub_text = "Natural acoustic and facial signals are consistent."
        bullet_1 = "• Facial landmarks align with audio frequencies across all frames"
        bullet_2 = "• No voice cloning or visual boundary artifacts found"
        action_text = "✅ NATURAL RECORDING VERIFIED"
        action_bg = (4, 120, 87)
    else: # NOT_VERIFIED / LIKELY NOT A SCAM
        bg_color = (22, 19, 13)
        panel_color = (34, 29, 20)
        accent_color = (245, 158, 11)     # Amber / Gold
        badge_bg = (217, 119, 6)
        badge_text = "⚠️ LIKELY NOT A SCAM"
        title_text = "Inconclusive Evidence"
        sub_text = "Could not verify official archives. Treat this video with extreme caution."
        bullet_1 = "• Real ministers and officials NEVER ask you to invest on WhatsApp"
        bullet_2 = "• Never send money to stranger UPI IDs or VIP trading groups"
        action_text = "🛡️ NEVER PAY STRANGERS ON WHATSAPP OR UPI"
        action_bg = (180, 83, 9)

    img = Image.new("RGB", (width, height), color=bg_color)
    draw = ImageDraw.Draw(img)

    # 1. Outer Border & Inner Panel
    draw.rounded_rectangle([18, 18, width - 18, height - 18], radius=24, outline=accent_color, width=4)
    draw.rounded_rectangle([32, 32, width - 32, height - 32], radius=20, fill=panel_color)

    font_badge = get_font(36, bold=True)
    font_title = get_font(46, bold=True)
    font_sub = get_font(26, bold=False)
    font_item = get_font(24, bold=False)
    font_action = get_font(28, bold=True)
    font_footer = get_font(18, bold=False)

    # 2. Top Header Badge
    badge_w = 660
    badge_h = 65
    draw.rounded_rectangle([60, 55, 60 + badge_w, 55 + badge_h], radius=14, fill=badge_bg)
    draw.text((85, 67), badge_text, fill=(255, 255, 255), font=font_badge)

    # FARQ Logo watermark top right
    draw.text((width - 240, 72), "FARQ FORENSICS", fill=(148, 163, 184), font=font_item)

    # 3. Title & Subtitle
    draw.text((60, 150), title_text, fill=(255, 255, 255), font=font_title)
    draw.text((60, 215), sub_text, fill=(203, 213, 225), font=font_sub)

    # 4. Details Box (Minimal, 2 bullets only)
    box_top = 280
    box_h = 190
    draw.rounded_rectangle([60, box_top, width - 60, box_top + box_h], radius=16, fill=(15, 20, 32), outline=(51, 65, 85), width=2)

    # Override bullet 1 or 2 with specific reason if present
    reasons = data.get("reasons") or []
    if reasons:
        txt = reasons[0].get("text", "") if isinstance(reasons[0], dict) else str(reasons[0])
        if txt:
            bullet_1 = "• " + txt[:110]

    original = data.get("original") or {}
    if original.get("found"):
        title = original.get("title") or "Official speech archive"
        bullet_2 = f"• Original Archive Found: {title} (0:00)"

    draw.text((90, box_top + 40), bullet_1, fill=(255, 255, 255), font=font_item)
    draw.text((90, box_top + 105), bullet_2, fill=(56, 189, 248) if "Archive" in bullet_2 else (203, 213, 225), font=font_item)

    # 5. Bottom Action Banner
    action_y = box_top + box_h + 30
    draw.rounded_rectangle([60, action_y, width - 60, action_y + 70], radius=14, fill=action_bg)
    draw.text((90, action_y + 18), action_text, fill=(255, 255, 255), font=font_action)

    # 6. Footer
    draw.text((60, height - 55), "FARQ Deepfake Verification · Track 3 Financial Cyber Security · IIT Delhi", fill=(100, 116, 139), font=font_footer)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    img.save(output_path, "PNG")
    print(output_path)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: generate_card.py '<json_data>' <output_path>")
        sys.exit(1)
    
    data_json = sys.argv[1]
    out_path = sys.argv[2]
    
    try:
        data = json.loads(data_json)
    except Exception as e:
        data = {"verdict": "NOT_VERIFIED", "headline": "Verification Output", "summary": str(e)}
        
    generate_verdict_card(data, out_path)
