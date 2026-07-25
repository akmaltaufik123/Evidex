import os
import asyncio
from datetime import datetime
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

# --- VERSION ---
__version__ = "1.0.1"

# --- ASCII ART BANNER ---
CYBEROPS_ASCII = r"""
_________        ___.                ________                
\_   ___ \___.__.\_ |__   ___________\_____  \ ______  ______
/    \  \<   |  | | __ \_/ __ \_  __ \/   |   \\____ \/  ___/
\     \___\___  | | \_\ \  ___/|  | \/    |    \  |_> >___ \ 
 \______  / ____| |___  /\___  >__|  \_______  /   __/____  >
        \/\/          \/     \/              \/|__|       \/ 
     
     CyberOps - Telegram Scraper for Investigation TSI (v1.0.1)
     Telegram personal message, channel, and groups scraper.
     Created by Bangmal. Strictly for lawful digital evidence collection.

     If you encouter a problem when running the tool by selecting option number 1
     it is because of your Telegram API_ID, API_HASH and PHONE_NUMBER not yet been
     fullfilled, obtain your Telegram API at official Telegram API portal here:
     https://my.telegram.org/
     
     Still facing the same problem? Any future collaboration? Contact me directly:

     Developer Contact:
     Name: Akmal Taufik
     Email: work.akmaltaufik@gmail.com
     LinkedIn: https://www.linkedin.com/in/akmaltaufik
"""

# --- CONFIGURATION ---
API_ID = ""
API_HASH = ""
PHONE_NUMBER = ""

SESSION_NAME = "cyberops_session"


def display_header():
    """Clears screen and prints persistent ASCII art, developer info, and capabilities summary."""
    print("\033[H\033[J", end="")  # Clear terminal screen for clean look
    print(CYBEROPS_ASCII)
    print("=" * 65)
    print("                   WELCOME TO CYBEROPS.TSI       ")
    print("=" * 65)
    print("")
    print(" [!] TOOL CAPABILITIES:")
    print("")
    print("   • Scrapes entire message history from Telegram channels and groups.")
    print("   • Extracts text messages, pictures, videos, documents, and audio/sounds.")
    print("   • Automatically stores structured outputs into a timestamped directory.")
    print("   • Provides live terminal review with 24-hour time format and day included.")
    print("   • Supports target lookup via usernames, links, or numeric IDs.")
    print("")
    print("=" * 65)


def show_legal_notice():
    """Reads and displays the legal notice from README_LEGAL.txt if available."""
    print("\n" + "~" * 65)
    print("                 LEGAL & CYBER CRIME ACT ADVISORY                ")
    print("~" * 65)
    if os.path.exists("README_LEGAL.txt"):
        with open("README_LEGAL.txt", "r", encoding="utf-8") as f:
            print(f.read())
    else:
        print("[-] Error: README_LEGAL.txt file not found in the current directory.")
    print("~" * 65)
    input("\nPress [Enter] to return to the Main Menu...")


def show_installation_guide():
    """Reads and displays the installation guide from README_INSTALL.txt if available."""
    print("\n" + "~" * 65)
    print("               INSTALLATION & ENVIRONMENT GUIDE               ")
    print("~" * 65)
    if os.path.exists("README_INSTALL.txt"):
        with open("README_INSTALL.txt", "r", encoding="utf-8") as f:
            print(f.read())
    else:
        print("[-] Error: README_INSTALL.txt file not found in the current directory.")
    print("~" * 65)
    input("\nPress [Enter] to return to the Main Menu...")


async def run_scraper():
    """Handles the core Telegram scraping logic."""
    print("\n[+] Initializing Telegram Client Session...")
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    
    try:
        await client.start(phone=PHONE_NUMBER)

        if not await client.is_user_authorized():
            try:
                await client.send_code_request(PHONE_NUMBER)
                code = input("Enter the verification code received on Telegram: ")
                await client.sign_in(PHONE_NUMBER, code)
            except SessionPasswordNeededError:
                password = input("Two-step verification is enabled. Enter your password: ")
                await client.sign_in(password=password)

        raw_target = input(
            "\nEnter Telegram Channel/Group username, link, or numeric ID (e.g., @channel or -100123456789): "
        ).strip()

        target_chat = raw_target
        if raw_target.lstrip("-").isdigit():
            target_chat = int(raw_target)

        current_time = datetime.now()
        folder_name = current_time.strftime("CyberOps_%Y-%m-%d_%H-%M-%S")
        os.makedirs(folder_name, exist_ok=True)
        media_folder = os.path.join(folder_name, "media")
        os.makedirs(media_folder, exist_ok=True)

        log_file_path = os.path.join(folder_name, "scraped_messages.txt")

        print(f"\n[+] Output directory created: {folder_name}/")
        print(f"[+] Scraping initiated. Live Terminal Review:\n")
        print("-" * 65)

        entity = await client.get_entity(target_chat)
        message_count = 0

        async for message in client.iter_messages(entity):
            message_count += 1

            msg_time = (
                message.date.strftime("%Y-%m-%d %H:%M:%S")
                if message.date
                else "Unknown Time"
            )
            sender_id = message.sender_id or "Unknown Sender"
            text_content = message.text or "[No Text / Media Message]"

            terminal_output = f"[{msg_time}] [Sender: {sender_id}] -> {text_content}"
            print(terminal_output)

            with open(log_file_path, "a", encoding="utf-8") as f:
                f.write(f"[{msg_time}] (ID: {message.id}) {sender_id}: {text_content}\n")

            if message.media:
                try:
                    file_path = await client.download_media(message, file=media_folder)
                    if file_path:
                        print(f"   [Media Saved] -> {os.path.basename(file_path)}")
                        with open(log_file_path, "a", encoding="utf-8") as f:
                            f.write(f"   [Media Saved]: {os.path.basename(file_path)}\n")
                except Exception as media_err:
                    print(f"   [Media Error] Failed to download: {media_err}")

        print("-" * 65)
        print(f"[+] Scraping complete! Total messages processed: {message_count}")
        print(f"[+] All logs and media saved securely inside: {folder_name}/")

    except Exception as e:
        print(f"[-] An error occurred during execution: {e}")
    finally:
        await client.disconnect()

    input("\nPress [Enter] to return to the Main Menu...")


async def main():
    while True:
        display_header()
        print("\nPlease select an option from the menu below:")
        print("")
        print("  [1] Run CyberOps.TSI")
        print("  [2] Read Legal Notice & Cyber Crime Act Guidelines")
        print("  [3] Read Installation for Telegram Set-up & Virtual Environment (venv) Guide")
        print("  [4] Exit Tool")
        
        choice = input("\nEnter your choice (1-4): ").strip()

        if choice == "1":
            await run_scraper()
        elif choice == "2":
            show_legal_notice()
        elif choice == "3":
            show_installation_guide()
        elif choice == "4":
            print("\nExiting CyberOps. Stay safe and compliant! Justice will prevail.")
            break
        else:
            input("\n[-] Invalid option! Please select between 1 and 4. Press [Enter] to try again...")


if __name__ == "__main__":
    asyncio.run(main())
