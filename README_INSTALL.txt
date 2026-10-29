
1. HOW TO OBTAIN TELEGRAM API CREDENTIALS (API ID & API HASH)
   To use EVIDEX, you must link your Telegram account using official
   developer credentials. Follow these steps to obtain them:
   
   * Step 1: Open your web browser and go to the official Telegram 
     developer portal at:
     https://my.telegram.org/
   
   * Step 2: Enter your phone number (including your country code, e.g., +60...) 
     and click "Next". Telegram will send an official confirmation code 
     to your Telegram application (saved messages / service notifications).
   
   * Step 3: Enter the confirmation code on the website and log into 
     your developer dashboard.
   
   * Step 4: Click on "API development tools".
   
   * Step 5: Fill out the application form to register a new application 
     (you can name it anything, e.g., "EvidexInvestigation").
     The platform type can be set to "Desktop".
   
   * Step 6: Once registered, the portal will display your unique:
     - api_id (an integer number)
     - api_hash (a secure alphanumeric string)
   
   * Step 7: Start EVIDEX and enter the credentials in the TUI. Credentials
     must not be pasted into the source code or committed to Git.


2. WHY USE A VIRTUAL ENVIRONMENT (venv)?
   While you can technically attempt to run Python scripts using your 
   global system package manager, it is strongly recommended to use a 
   Python Virtual Environment (`venv`). A virtual environment isolates 
   project dependencies (such as Telethon) preventing conflicts with 
   global system Python packages or breaking operating system updates.


3. STEP-BY-STEP SETUP & INSTALLATION INSTRUCTIONS (Linux / WSL / Ubuntu):
   
   Step 1: Open your terminal inside the project folder.
   
   Step 2: Create a virtual environment named 'venv':
           python3 -m venv venv

   Step 3: Activate the virtual environment:
           source venv/bin/activate
           *(Note: Your terminal prompt should now display (venv))*

   Step 4: Upgrade pip and install the dependencies using the 
           provided `requirements.txt` file:
           pip install --upgrade pip
           pip install -r requirements.txt


4. RUNNING THE TOOL:
   Once installed inside the virtual environment, execute the script via:
           python3 evidex.py

   Optional localhost browser mode (same TUI):
           python3 -m pip install -r requirements-web.txt
           python3 evidex.py --web
   Open http://127.0.0.1:8000 (or use --port 8080).
   Use one tab; do not share a Telegram session with another running instance.
   Cancel and wait for finalization before refreshing/closing an active tab.
   Keep the server terminal open; stop it with Ctrl+C when finished.
   Exports are saved on the Python host, not downloaded by the browser.


5. CAN YOU RUN WITHOUT VENV?
   Yes, terminals will technically execute scripts without a venv if 
   libraries are installed globally. However, using `venv` remains
   the industry best-practice for security and stability.


6. OPTIONAL ENVIRONMENT VARIABLES:
   EVIDEX can prefill its credential fields without modifying source code:
           TELEGRAM_API_ID
           TELEGRAM_API_HASH
           TELEGRAM_PHONE

   Optional path settings:
           EVIDEX_EXPORT_DIR
           EVIDEX_SESSION_DIR
           EVIDEX_SESSION_PATH
           EVIDEX_PROXY_URL

   EVIDEX_PROXY_URL accepts a SOCKS5, SOCKS4, or HTTP proxy URL. Example:
           socks5://username:password@proxy-host:port

   Protect the session directory. A Telegram session file grants account access
   and must be handled as a credential.

7. REUSING AN EXISTING TELETHON SESSION:
   If a previous Telethon tool already connects successfully, close that tool
   and enter the absolute path to its `.session` file in EVIDEX. This reuses the
   authorized key and working Telegram data-center assignment. Never run two
   programs against the same session file at the same time.

8. CONNECTION CHECK (NO LOGIN):
           python3 evidex.py --check-connection
   Enter your API ID and masked API hash. This uses a fresh in-memory session
   with a direct connection, without touching saved sessions or logging in.
   Terminal and browser extraction share telegram_connection.py.
   Proxy and existing-session selection are explicit; ALL_PROXY and nearby
   session files are no longer picked automatically.
   Optional EVIDEX_CONNECT_TIMEOUT sets the attempt budget (1 to 300 seconds).
