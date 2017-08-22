#Zabbix alert bot for telegram

1. Install redis-server:
   ```
    apt install redis-server
    systemctl enable redis-server
    systemctl start redis-server
    ```
2. Clone global brunch to your server
    ```
    git clone -b global https://github.com/amalgamm/zabbix_tg_bot.git
    ```
3. Enter Telegram Bot directory
    ```
    cd zabbix_tg_bot/
    ```
4. Install requirements packages
    ```
    pip3 install -r requirements.txt
    ```
5. create and edit config.py file:
    ```
    token = 'FILL THIS FIELD' # Copy Telegram API token here
    
    redis_server = 'FILL THIS FIELD' # Redis-server ip address
    redis_db = 0 # Redis-server database number
    listen_int = '0.0.0.0' # WebServer listeting interface, used for zabbix incoming messages
    listen_port = 4000 # WebServer listening port, used for zabbix incoming messages
    ```
6. run bot with python3 app.py or create service