import sqlite3
import datetime
import os

def migrate():
    old_db = input('путь к старым бд: ')
    new_db = input('путь к новым бд: ')
    if not os.path.exists(old_db):
        print(f'старая бд не найдена: {old_db}')
        return
    if not os.path.exists(new_db):
        print(f'новая бд не найдена: {new_db}')
        return
    conn_old = sqlite3.connect(old_db)
    conn_new = sqlite3.connect(new_db)
    cur_old = conn_old.cursor()
    cur_new = conn_new.cursor()
    print('перенос юзеров')
    
    cur_old.execute('PRAGMA table_info("users")')
    columns = [col[1] for col in cur_old.fetchall()]
    has_taurgems = 'taurgems' in columns
    
    query = f"SELECT user_id, first_name, username, is_admin, taurons, taurcoins{', taurgems' if has_taurgems else ''} FROM users"
    cur_old.execute(query)
    users = cur_old.fetchall()
    users_migrated = 0
    for u in users:
        if has_taurgems:
            user_id, first_name, username, is_admin, taurons, taurcoins, taurgems = u
        else:
            user_id, first_name, username, is_admin, taurons, taurcoins = u
            taurgems = 0
        is_admin_int = 1 if is_admin else 0
        try:
            cur_new.execute('\n                INSERT OR IGNORE INTO users (telegram_id, full_name, username, is_admin, taurons, taurcoins, taurgems)\n                VALUES (?, ?, ?, ?, ?, ?, ?)\n            ', (user_id, first_name or '', username, is_admin_int, taurons or 0, taurcoins or 0, taurgems or 0))
            users_migrated += 1
        except Exception as e:
            print(f'ошибка переноса юзеров {user_id}: {e}')
    print(f'перенесли {users_migrated} пользователей')
    print('переносим миссии')
    cur_old.execute('SELECT user_id, mission_id, status, report_data, timestamp FROM user_missions')
    missions = cur_old.fetchall()
    missions_migrated = 0
    for m in missions:
        user_id, mission_id, status, report_data, ts = m
        if not ts:
            ts_str = str(datetime.datetime.now())
        elif isinstance(ts, (int, float)):
            ts_str = str(datetime.datetime.fromtimestamp(float(ts)))
        else:
            ts_str = str(ts)
        try:
            cur_new.execute('\n                INSERT OR IGNORE INTO user_missions (user_id, mission_id, status, report_data, timestamp)\n                VALUES (?, ?, ?, ?, ?)\n            ', (user_id, mission_id, status or 'pending', report_data or '', ts_str))
            missions_migrated += 1
        except Exception as e:
            print(f'ошибка переноса миссии {user_id}-{mission_id}: {e}')
    print(f'перенесли {missions_migrated} миссий')
    print('переносим параметры')
    cur_old.execute('SELECT name, value FROM parametrs')
    params = cur_old.fetchall()
    params_migrated = 0
    for p in params:
        name, value = p
        try:
            cur_new.execute('\n                INSERT OR REPLACE INTO parametrs (name, value)\n                VALUES (?, ?)\n            ', (name, value))
            params_migrated += 1
        except Exception as e:
            print(f'ошибка переноса параметра {name}: {e}')
    print(f'перенесли {params_migrated} параметров')
    conn_new.commit()
    conn_old.close()
    conn_new.close()
    print('миграция завершена')
if __name__ == '__main__':
    migrate()