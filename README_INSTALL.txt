
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

   Protect the session directory. A Telegram session file grants account access
   and must be handled as a credential.
