import os
import json
import re
import subprocess
import threading
import time
import traceback
from contextlib import closing
from datetime import datetime

import mysql.connector
import requests
import tkinter as tk
from tkinter import messagebox, ttk

try:
    from pymodbus.client.sync import ModbusSerialClient
except Exception:
    ModbusSerialClient = None

try:
    import ttkbootstrap as tb

    USE_BOOTSTRAP = True
except Exception:
    tb = None
    USE_BOOTSTRAP = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_HOST = os.getenv('AUTO_BATCH_DB_HOST', 'localhost')
DB_USER = os.getenv('AUTO_BATCH_DB_USER', 'root')
DB_PASS = os.getenv('AUTO_BATCH_DB_PASS', 'sunfra')
DB_NAME = os.getenv('AUTO_BATCH_DB_NAME', 'auto_batching')
CLIENT_ID = 12

HTTP_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (X11; Linux armv7l) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept': 'application/json,text/plain,*/*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Connection': 'keep-alive',
}


def get_conn():
    return mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME,
        autocommit=False,
    )


def fetchall(query, params=()):
    try:
        with closing(get_conn()) as conn:
            with closing(conn.cursor(dictionary=True)) as cur:
                cur.execute(query, params)
                return cur.fetchall()
    except Exception as exc:
        print(f'[DB READ ERROR] {exc}')
        print(f'[DB READ QUERY] {query}')
        return []


def execute(query, params=()):
    with closing(get_conn()) as conn:
        with closing(conn.cursor()) as cur:
            cur.execute(query, params)
            conn.commit()


def executemany(query, rows):
    if not rows:
        return
    with closing(get_conn()) as conn:
        with closing(conn.cursor()) as cur:
            cur.executemany(query, rows)
            conn.commit()


def now_date():
    return datetime.now().strftime('%Y-%m-%d')


def table_client_id(table_name, preferred=CLIENT_ID):
    return CLIENT_ID


def normalize_shead(name):
    return '_'.join(name.strip().lower().split())


def get_sheads(client_id=None):
    cid = table_client_id('shead_config') if client_id is None else client_id
    return fetchall(
        'SELECT shead_name FROM shead_config WHERE client_id=%s ORDER BY id ASC',
        (cid,),
    )


def get_material_options():
    cid = table_client_id('feed_rawmaterial')
    primary = fetchall(
        "SELECT name FROM feed_rawmaterial WHERE client_id=%s AND LOWER(type)='raw material' ORDER BY name",
        (cid,),
    )
    if primary:
        return [x['name'] for x in primary]

    fallback = fetchall(
        'SELECT name FROM feed_rawmaterial WHERE client_id=%s ORDER BY name',
        (cid,),
    )
    return [x['name'] for x in fallback]


def ensure_formula_seed():
    formula_cid = table_client_id('feed_formula_detail')
    shead_cid = table_client_id('shead_config')
    sheads = [normalize_shead(x['shead_name']) for x in get_sheads(shead_cid)]
    if not sheads:
        return

    existing = fetchall(
        'SELECT id FROM feed_formula_detail WHERE client_id=%s LIMIT 1',
        (formula_cid,),
    )
    if existing:
        return

    materials = get_material_options()
    if not materials:
        return

    rows = []
    for shead in sheads:
        for mat in materials:
            rows.append((formula_cid, mat, 'Feed_Formula', shead, 0))
            rows.append((formula_cid, mat, 'Feed_Medicine', shead, 0))

    executemany(
        '''INSERT INTO feed_formula_detail
           (client_id, feed_rawMaterial_name, type, feed_formulaType, quantity)
           VALUES (%s,%s,%s,%s,%s)''',
        rows,
    )


def get_dashboard_data(selected_date):
    shead_cid = table_client_id('shead_config')
    sheads = [x['shead_name'] for x in get_sheads(shead_cid)]
    counts = {s: 0 for s in sheads}
    if sheads:
        placeholders = ','.join(['%s'] * len(sheads))
        rows = fetchall(
            f'''SELECT shead_name, COUNT(*) AS cnt
                FROM batching_running_logs
                WHERE DATE(date)=%s AND shead_name IN ({placeholders})
                GROUP BY shead_name''',
            tuple([selected_date] + sheads),
        )
        for row in rows:
            counts[row['shead_name']] = int(row['cnt'])

    mats = fetchall('SELECT * FROM feed_rawmaterial ORDER BY type, name')
    raw = [m for m in mats if (m.get('type') or '').strip().lower() == 'raw material']
    med = [m for m in mats if m not in raw]
    return counts, raw, med


def get_feed_formula_structured():
    ensure_formula_seed()
    formula_cid = table_client_id('feed_formula_detail')
    shead_cid = table_client_id('shead_config')
    sheads = [normalize_shead(x['shead_name']) for x in get_sheads(shead_cid)]
    formula_shead_rows = fetchall(
        'SELECT DISTINCT feed_formulaType FROM feed_formula_detail WHERE client_id=%s ORDER BY feed_formulaType',
        (formula_cid,),
    )
    formula_sheads = [x['feed_formulaType'] for x in formula_shead_rows if x.get('feed_formulaType')]

    if not sheads:
        sheads = formula_sheads
    if not sheads:
        return []

    sum_fields = ', '.join(
        [f"SUM(CASE WHEN feed_formulaType='{s}' THEN quantity ELSE 0 END) AS `{s}`" for s in sheads]
    )
    rows = fetchall(
        f'''SELECT type, feed_rawMaterial_name AS material, {sum_fields}
            FROM feed_formula_detail
            WHERE client_id=%s
            GROUP BY type, feed_rawMaterial_name
            ORDER BY FIELD(type, 'Feed_Formula', 'Feed_Medicine')''',
        (formula_cid,),
    )

    out = {s: {'Feed_Formula': {}, 'Feed_Medicine': {}} for s in sheads}
    for row in rows:
        t = row['type']
        if t not in ('Feed_Formula', 'Feed_Medicine'):
            continue
        material = row['material']
        for s in sheads:
            out[s][t][material] = float(row.get(s) or 0)
    return [{k: v} for k, v in out.items()]


def upsert_formula(data):
    formula_cid = table_client_id('feed_formula_detail')
    with closing(get_conn()) as conn:
        with closing(conn.cursor()) as cur:
            for shead_obj in data:
                for shead, payload in shead_obj.items():
                    shead_key = (shead or '').strip()
                    for type_name in ('Feed_Formula', 'Feed_Medicine'):
                        for material, qty in (payload.get(type_name) or {}).items():
                            material_name = (material or '').strip()
                            quantity = float(qty or 0)
                            # Atomic upsert: avoids duplicate-key issues and updates even when value is unchanged.
                            cur.execute(
                                '''INSERT INTO feed_formula_detail
                                   (feed_formulaType, quantity, feed_rawMaterial_name, type, client_id)
                                   VALUES (%s,%s,%s,%s,%s)
                                   ON DUPLICATE KEY UPDATE quantity=VALUES(quantity)''',
                                (shead_key, quantity, material_name, type_name, formula_cid),
                            )
            conn.commit()


def add_new_material(material, type_name):
    formula_cid = table_client_id('feed_formula_detail')
    shead_cid = table_client_id('shead_config')
    sheads = [normalize_shead(x['shead_name']) for x in get_sheads(shead_cid)]
    rows = []
    for s in sheads:
        exists = fetchall(
            '''SELECT id FROM feed_formula_detail
               WHERE client_id=%s AND feed_rawMaterial_name=%s AND type=%s AND feed_formulaType=%s''',
            (formula_cid, material, type_name, s),
        )
        if not exists:
            rows.append((formula_cid, material, type_name, s, 0))

    executemany(
        '''INSERT INTO feed_formula_detail
           (client_id, feed_rawMaterial_name, type, feed_formulaType, quantity)
           VALUES (%s,%s,%s,%s,%s)''',
        rows,
    )


def update_shead_counts(shead_count, chick_count, grower_count):
    shead_cid = table_client_id('shead_config')
    execute('DELETE FROM shead_config WHERE client_id=%s', (shead_cid,))
    rows = []
    for i in range(1, shead_count + 1):
        rows.append((f'Shead {i}', f'Shead Number: {i}', shead_cid))
    for i in range(1, chick_count + 1):
        rows.append((f'Chick {i}', f'Chick Number: {i}', shead_cid))
    for i in range(1, grower_count + 1):
        rows.append((f'Grower {i}', f'Grower Number: {i}', shead_cid))

    executemany(
        'INSERT INTO shead_config (shead_name, description, client_id) VALUES (%s,%s,%s)',
        rows,
    )


def save_motor_config(materials):
    motor_cid = table_client_id('motor_config')
    execute('DELETE FROM motor_config WHERE client_id=%s', (motor_cid,))
    rows = []
    total = len(materials)
    for idx, material in enumerate(materials, start=1):
        rows.append((idx, material, motor_cid, total))

    executemany(
        '''INSERT INTO motor_config (motor_number, material_name, client_id, number_of_motor)
           VALUES (%s,%s,%s,%s)''',
        rows,
    )


def get_motor_config():
    motor_cid = table_client_id('motor_config')
    return fetchall(
        '''SELECT motor_number, material_name, number_of_motor
           FROM motor_config WHERE client_id=%s ORDER BY motor_number''',
        (motor_cid,),
    )


def get_report(filter_key='today', selected_shead='All', from_date=None, to_date=None):
    base_cond = {
        'today': 'DATE(date)=CURDATE()',
        'yesterday': 'DATE(date)=CURDATE()-INTERVAL 1 DAY',
        'weekly': 'YEARWEEK(date,1)=YEARWEEK(CURDATE(),1)',
        'monthly': 'YEAR(date)=YEAR(CURDATE()) AND MONTH(date)=MONTH(CURDATE())',
        'yearly': 'YEAR(date)=YEAR(CURDATE())',
    }.get(filter_key, 'DATE(date)=CURDATE()')
    shead_params = []
    if filter_key == 'custom' and from_date and to_date:
        base_cond = 'DATE(date) BETWEEN %s AND %s'
        shead_params.extend([from_date, to_date])

    shead_cond = base_cond
    if selected_shead != 'All':
        shead_cond += ' AND shead_name=%s'
        shead_params.append(selected_shead)

    shead_rows = fetchall(
        f'''SELECT DATE(date) AS log_date, shead_name, COUNT(*) AS cnt
            FROM batching_running_logs
            WHERE {shead_cond}
            GROUP BY DATE(date), shead_name
            ORDER BY log_date DESC, shead_name ASC''',
        tuple(shead_params),
    )

    shead_data = {}
    for r in shead_rows:
        shead_data.setdefault(str(r['log_date']), {})[r['shead_name']] = int(r['cnt'])

    material_cond = base_cond.replace('date', 'timestamp')
    material_params = []
    if filter_key == 'custom' and from_date and to_date:
        material_params = [from_date, to_date]

    mat_rows = fetchall(
        f'''SELECT DATE(timestamp) AS log_date, material_name, SUM(reduced_quantity) AS qty
            FROM feed_material_reduction_logs
            WHERE {material_cond}
            GROUP BY DATE(timestamp), material_name
            ORDER BY log_date DESC, material_name ASC''',
        tuple(material_params),
    )
    mat_data = {}
    for r in mat_rows:
        mat_data.setdefault(str(r['log_date']), {})[r['material_name']] = float(r['qty'] or 0)

    materials = [x['material_name'] for x in fetchall('SELECT DISTINCT material_name FROM feed_material_reduction_logs ORDER BY material_name')]
    return shead_data, mat_data, materials


def get_batch_feed_types():
    rows = fetchall(
        'SELECT shead_name FROM shead_config WHERE client_id=%s ORDER BY id',
        (CLIENT_ID,),
    )
    return [r['shead_name'] for r in rows]


def get_motor_materials_for_batch():
    rows = fetchall(
        'SELECT motor_number, material_name FROM motor_config WHERE client_id=%s ORDER BY motor_number',
        (CLIENT_ID,),
    )
    return rows


def get_formula_for_feed(feed_name):
    feed_key = normalize_shead(feed_name)
    rows = fetchall(
        '''SELECT feed_rawMaterial_name, quantity
           FROM feed_formula_detail
           WHERE client_id=%s AND type='Feed_Formula' AND feed_formulaType=%s''',
        (CLIENT_ID, feed_key),
    )
    return {r['feed_rawMaterial_name']: float(r['quantity'] or 0) for r in rows}


def insert_running_log(feed_name):
    execute(
        '''INSERT INTO batching_running_logs (shead_name, ton, client_id, date, status)
           VALUES (%s, %s, %s, %s, %s)''',
        (feed_name, 1, CLIENT_ID, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'running'),
    )


def get_mac_address_dash():
    for path in ('/sys/class/net/wlan0/address', '/sys/class/net/eth0/address'):
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return f.read().strip().replace(':', '-')
    return '00-00-00-00-00-00'


def fetch_json_or_raise(url, timeout=20):
    try:
        resp = requests.get(url, headers=HTTP_HEADERS, timeout=timeout, allow_redirects=True)
    except requests.RequestException as exc:
        raise Exception(f'Network error for {url}: {exc}') from exc

    if resp.status_code != 200:
        preview = (resp.text or '').strip().replace('\n', ' ')[:220]
        raise Exception(f'HTTP {resp.status_code} from {url}. Response: {preview}')

    text = resp.text or ''
    try:
        return resp.json()
    except ValueError:
        pass

    # Some servers prepend warnings/HTML around JSON; try to extract the first JSON block.
    match = re.search(r'(\{.*\}|\[.*\])', text, re.S)
    if match:
        candidate = match.group(1).strip()
        try:
            return json.loads(candidate)
        except ValueError:
            pass

    preview = text.strip().replace('\n', ' ')[:220]
    raise Exception(
        f'Invalid JSON from {url}. '
        f'Raw response starts with: {preview if preview else "<empty response>"}'
    )


def restart_apache():
    commands = [
        ['sudo', 'systemctl', 'restart', 'apache2'],
        ['sudo', 'service', 'apache2', 'restart'],
        ['systemctl', 'restart', 'apache2'],
        ['service', 'apache2', 'restart'],
    ]
    for cmd in commands:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            if result.returncode == 0:
                print(f'[APACHE] Restart successful via: {" ".join(cmd)}')
                return True
        except Exception:
            continue
    print('[APACHE] Restart failed. Please check apache2 service and permissions.')
    return False


def prune_formula_types_to_shead_config():
    formula_cid = table_client_id('feed_formula_detail')
    shead_cid = table_client_id('shead_config')
    allowed = {normalize_shead(x['shead_name']) for x in get_sheads(shead_cid)}
    if not allowed:
        return

    rows = fetchall(
        'SELECT DISTINCT feed_formulaType FROM feed_formula_detail WHERE client_id=%s',
        (formula_cid,),
    )
    stale = []
    for row in rows:
        key = (row.get('feed_formulaType') or '').strip()
        if key and key not in allowed:
            stale.append(key)

    if not stale:
        return

    placeholders = ','.join(['%s'] * len(stale))
    execute(
        f'''DELETE FROM feed_formula_detail
            WHERE client_id=%s AND feed_formulaType IN ({placeholders})''',
        tuple([formula_cid] + stale),
    )
    print(f'[SYNC] Removed stale formula types not in shead config: {", ".join(stale)}')


def sync_from_cloud(mac_address):
    formula_url = f'https://sunfra.com/farm/csv/feed_formula_json.php?mac_address={mac_address}'
    shead_url = f'https://sunfra.com/farm/csv/shead_chick_grower_json.php?mac_address={mac_address}'
    raw_url = f'https://sunfra.com/farm/csv/feed_raw_material_json.php?mac_address={mac_address}'

    f_data = fetch_json_or_raise(formula_url, timeout=20)
    if not isinstance(f_data, list):
        raise Exception(f'Unexpected formula payload type from API: {type(f_data).__name__}')
    execute('DELETE FROM feed_formula_detail')
    rows = [
        (
            x['id'],
            x['feed_formulaType'],
            x['quantity'],
            x['feed_rawMaterial_name'],
            x['type'],
            x['client_id'],
        )
        for x in f_data
    ]
    executemany(
        '''INSERT INTO feed_formula_detail
           (id, feed_formulaType, quantity, feed_rawMaterial_name, type, client_id)
           VALUES (%s,%s,%s,%s,%s,%s)''',
        rows,
    )

    s_data = fetch_json_or_raise(shead_url, timeout=20)
    if not isinstance(s_data, list):
        raise Exception(f'Unexpected shead payload type from API: {type(s_data).__name__}')
    execute('DELETE FROM shead_config')
    rows = [(x['id'], x['shead_name'], x['description'], x['client_id']) for x in s_data]
    executemany(
        'INSERT INTO shead_config (id, shead_name, description, client_id) VALUES (%s,%s,%s,%s)',
        rows,
    )
    prune_formula_types_to_shead_config()

    r_data = fetch_json_or_raise(raw_url, timeout=20)
    if not isinstance(r_data, dict):
        raise Exception(f'Unexpected raw material payload type from API: {type(r_data).__name__}')
    if 'material' not in r_data:
        raise Exception('Raw material JSON missing "material" key.')
    execute('DELETE FROM feed_rawmaterial')
    rows = []
    for m in r_data.get('material', []):
        rows.append((m['name'], float(m['stock']), m.get('metric', 'kg'), m['type'], int(m['client_id'])))
    executemany(
        'INSERT INTO feed_rawmaterial (name, stock, metrics, type, client_id) VALUES (%s,%s,%s,%s,%s)',
        rows,
    )
    push_report = push_running_logs_to_cloud(mac_address)
    print(
        '[SYNC] Running logs push summary: '
        f"total={push_report['total']}, sent={push_report['sent']}, "
        f"failed={push_report['failed']}, skipped={push_report['skipped']}"
    )
    return push_report


def push_running_logs_to_cloud(mac_address):
    rows = fetchall(
        '''SELECT DATE(date) AS log_date, shead_name, COUNT(*) AS running_count
           FROM batching_running_logs
           WHERE status='running' AND client_id=%s
           GROUP BY DATE(date), shead_name
           ORDER BY shead_name, log_date''',
        (CLIENT_ID,),
    )
    if not rows:
        print('[SYNC] No running logs found to send.')
        return {'total': 0, 'sent': 0, 'failed': 0, 'skipped': 0}

    api_url = 'https://sunfra.com/farm/sunfra/sensor/feed_feeding_to_shead_through_auto_batching.php'
    sent = 0
    failed = 0
    skipped = 0
    for row in rows:
        shead_name = (row.get('shead_name') or '').strip()
        log_date = str(row.get('log_date') or '').strip()
        count = float(row.get('running_count') or 0)

        if not shead_name or not log_date:
            skipped += 1
            print(f'[SYNC] Skipping invalid running log row: {row}')
            continue

        try:
            resp = requests.get(
                api_url,
                params={
                    'sheadNo': shead_name,
                    'tons': count,
                    'mac_address': mac_address,
                },
                headers=HTTP_HEADERS,
                timeout=20,
                allow_redirects=True,
            )
            if resp.status_code != 200:
                failed += 1
                print(f'[SYNC] Running-log push failed (HTTP {resp.status_code}) for {shead_name} ({log_date})')
                continue

            payload = None
            try:
                payload = resp.json()
            except ValueError:
                match = re.search(r'(\{.*\}|\[.*\])', resp.text or '', re.S)
                if match:
                    try:
                        payload = json.loads(match.group(1).strip())
                    except ValueError:
                        payload = None

            is_ok = isinstance(payload, dict) and str(payload.get('status', '')).lower() == 'ok'
            if is_ok:
                execute(
                    '''UPDATE batching_running_logs
                       SET status='Done'
                       WHERE client_id=%s AND status='running' AND shead_name=%s AND DATE(date)=%s''',
                    (CLIENT_ID, shead_name, log_date),
                )
                sent += 1
                print(f'[SYNC] Running-log push success for {shead_name} ({log_date})')
            else:
                failed += 1
                preview = (resp.text or '').strip().replace('\n', ' ')[:220]
                print(f'[SYNC] Running-log push failed for {shead_name} ({log_date}). Response: {preview}')
        except requests.RequestException as exc:
            failed += 1
            print(f'[SYNC] Running-log push network error for {shead_name} ({log_date}): {exc}')

    return {'total': len(rows), 'sent': sent, 'failed': failed, 'skipped': skipped}


class AutoBatchingDesktop:
    def __init__(self):
        if USE_BOOTSTRAP:
            self.root = tb.Window(themename='cosmo')
        else:
            self.root = tk.Tk()

        self.root.title('Auto Batching Python Control Panel')
        self.root.configure(bg='#ADD8E6')

        self.colors = {
            'bg': '#ADD8E6',
            'surface': '#ADD8E6',
            'sidebar': '#0f2747',
            'sidebar_btn': '#173a66',
            'sidebar_active': '#1b8f6b',
            'text_light': '#f4f8ff',
            'title': '#102a43',
            'muted': '#486581',
            'accent': '#1b8f6b',
            'accent_soft': '#d1fae5',
            'danger': '#c92a2a',
        }

        self.current_frame = None
        self.formula_data = []
        self.motor_material_vars = []
        self.formula_status = None
        self.menu_buttons = {}
        self.active_menu = None
        self.formula_editor = None
        self.formula_editor_item = None
        self.formula_editor_col = None
        self.batch_thread = None
        self.batch_stop_event = threading.Event()
        self.batch_running = False
        self.current_batch_feed = None
        self.proc_status = tk.StringVar(value='Stopped')
        self.proc_pid = tk.StringVar(value='Integrated')
        self.batch_current_var = tk.StringVar(value='Currently Running Material: None')
        self.batch_current_weight_var = tk.StringVar(value='Material Quantity: 0')
        self.batch_expected_var = tk.StringVar(value='Cumulative Expected Weight: 0')
        self.batch_indicator_var = tk.StringVar(value='Live Indicator: N/A')
        self.batch_log_text = None
        self.batch_feed_buttons = []
        self.batch_feed_button_map = {}
        self.batch_material_tree = None
        self.relay_client = None
        self.indicator_client = None
        self.batch_view_active = False
        self.indicator_poll_job = None
        self.modbus_lock = threading.Lock()
        self.last_indicator_value = None
        self.last_indicator_ts = 0.0
        self.root.tk_setPalette(background=self.colors['bg'])
        self._fit_to_display()

        self._layout()
        self.switch_page('Home', self.show_home)

    def _fit_to_display(self):
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        # Keep a small top/bottom margin to avoid clipping on touch displays.
        target_w = max(800, screen_w)
        target_h = max(480, screen_h - 24)
        self.root.geometry(f'{target_w}x{target_h}+0+0')
        self.root.minsize(min(980, target_w), min(580, target_h))
        try:
            # Linux/RPi friendly maximize path.
            self.root.attributes('-zoomed', True)
        except Exception:
            try:
                # Fallback.
                self.root.state('zoomed')
            except Exception:
                pass

    def _section_title(self, parent, text, subtext=''):
        bar = tk.Frame(parent, bg=self.colors['bg'])
        bar.pack(fill='x', padx=14, pady=(10, 8))
        tk.Label(
            bar,
            text=text,
            bg=self.colors['bg'],
            fg=self.colors['title'],
            font=('Segoe UI', 19, 'bold'),
        ).pack(side='left')
        if subtext:
            tk.Label(
                bar,
                text=subtext,
                bg=self.colors['bg'],
                fg=self.colors['muted'],
                font=('Segoe UI', 10),
            ).pack(side='left', padx=10, pady=(8, 0))
        return bar

    def _card(self, parent, padx=12, pady=12):
        card = tk.Frame(parent, bg=self.colors['surface'], bd=0, highlightthickness=1, highlightbackground='#d7e2f0')
        card.pack(fill='both', expand=True, padx=padx, pady=pady)
        return card

    def switch_page(self, title, callback):
        self.active_menu = title
        for label, btn in self.menu_buttons.items():
            if label == title:
                btn.configure(bg=self.colors['sidebar_active'])
            else:
                btn.configure(bg=self.colors['sidebar_btn'])
        # Always switch view immediately, then load page async to keep UI responsive.
        self.clear_content()
        loading = tk.Label(
            self.current_frame,
            text=f'Opening {title}...',
            bg=self.colors['bg'],
            fg=self.colors['title'],
            font=('Segoe UI', 13, 'bold'),
        )
        loading.pack(anchor='center', expand=True)
        self.root.update_idletasks()
        self.root.after(10, lambda: self._open_page(title, callback))

    def _open_page(self, title, callback):
        try:
            callback()
            self.root.update_idletasks()
        except Exception as exc:
            print(f'[NAV ERROR] Failed to open "{title}": {exc}')
            traceback.print_exc()
            self.clear_content()
            box = tk.Frame(self.current_frame, bg=self.colors['surface'], highlightthickness=1, highlightbackground='#d7e2f0')
            box.pack(fill='both', expand=True, padx=18, pady=18)
            tk.Label(
                box,
                text=f'Unable to open "{title}"',
                bg=self.colors['surface'],
                fg=self.colors['danger'],
                font=('Segoe UI', 16, 'bold'),
            ).pack(anchor='w', padx=14, pady=(14, 6))
            tk.Label(
                box,
                text=str(exc),
                bg=self.colors['surface'],
                fg=self.colors['title'],
                justify='left',
                wraplength=760,
                font=('Segoe UI', 11),
            ).pack(anchor='w', padx=14, pady=(0, 14))
            self.root.update_idletasks()

    def _layout(self):
        self.sidebar = tk.Frame(self.root, bg=self.colors['sidebar'], width=210)
        self.sidebar.pack(side='left', fill='y')
        self.sidebar.pack_propagate(False)

        tk.Label(
            self.sidebar,
            text='Auto Batching',
            fg=self.colors['text_light'],
            bg=self.colors['sidebar'],
            font=('Segoe UI', 18, 'bold'),
        ).pack(pady=(16, 2))
        tk.Label(
            self.sidebar,
            text='Control Center',
            fg='#9fb3c8',
            bg=self.colors['sidebar'],
            font=('Segoe UI', 10),
        ).pack(pady=(0, 14))

        menu = [
            ('Home', self.show_home),
            ('Configuration', self.show_configuration),
            ('Feed Formula', self.show_feed_formula),
            ('Report', self.show_report),
            ('Auto Batching', self.show_auto_batching),
        ]

        for title, command in menu:
            btn = tk.Button(
                self.sidebar,
                text=f'  {title}',
                command=lambda t=title, c=command: self.switch_page(t, c),
                anchor='w',
                padx=14,
                pady=8,
                relief='flat',
                bd=0,
                bg=self.colors['sidebar_btn'],
                fg=self.colors['text_light'],
                activebackground=self.colors['sidebar_active'],
                activeforeground='white',
                font=('Segoe UI', 11, 'bold'),
                cursor='hand2',
            )
            btn.pack(fill='x', pady=4, padx=10)
            self.menu_buttons[title] = btn

        tk.Button(
            self.sidebar,
            text='Sync From Cloud',
            command=self.sync_cloud,
            anchor='w',
            padx=14,
            pady=8,
            relief='flat',
            bd=0,
            bg='#246eb9',
            fg='white',
            activebackground='#1f8aeb',
            font=('Segoe UI', 11, 'bold'),
            cursor='hand2',
        ).pack(fill='x', pady=16, padx=10)

        live_card = tk.Frame(
            self.sidebar,
            bg='#123154',
            bd=0,
            highlightthickness=1,
            highlightbackground='#2c5a8e',
        )
        live_card.pack(fill='x', padx=10, pady=(0, 12))
        tk.Label(
            live_card,
            text='Live Batching',
            bg='#123154',
            fg='white',
            font=('Segoe UI', 11, 'bold'),
        ).pack(anchor='w', padx=10, pady=(8, 2))
        tk.Label(
            live_card,
            textvariable=self.proc_status,
            bg='#123154',
            fg='#bde7ff',
            font=('Segoe UI', 10, 'bold'),
        ).pack(anchor='w', padx=10, pady=(0, 4))
        tk.Label(
            live_card,
            textvariable=self.batch_current_var,
            bg='#123154',
            fg='white',
            wraplength=180,
            justify='left',
            font=('Segoe UI', 9),
        ).pack(anchor='w', padx=10, pady=(0, 2))
        tk.Label(
            live_card,
            textvariable=self.batch_current_weight_var,
            bg='#123154',
            fg='white',
            wraplength=180,
            justify='left',
            font=('Segoe UI', 9),
        ).pack(anchor='w', padx=10, pady=(0, 2))
        tk.Label(
            live_card,
            textvariable=self.batch_expected_var,
            bg='#123154',
            fg='white',
            wraplength=180,
            justify='left',
            font=('Segoe UI', 9),
        ).pack(anchor='w', padx=10, pady=(0, 2))
        tk.Label(
            live_card,
            textvariable=self.batch_indicator_var,
            bg='#123154',
            fg='#7dffbf',
            wraplength=180,
            justify='left',
            font=('Segoe UI', 9, 'bold'),
        ).pack(anchor='w', padx=10, pady=(0, 10))

        self.content = tk.Frame(self.root, bg=self.colors['bg'])
        self.content.pack(side='right', fill='both', expand=True)
        style = ttk.Style()
        try:
            style.configure('Treeview', rowheight=34, font=('Segoe UI', 11), background=self.colors['surface'], fieldbackground=self.colors['surface'])
            style.configure('Treeview.Heading', font=('Segoe UI', 11, 'bold'))
        except Exception:
            pass

    def clear_content(self):
        self.batch_view_active = False
        if self.indicator_poll_job is not None and not self.batch_running:
            try:
                self.root.after_cancel(self.indicator_poll_job)
            except Exception:
                pass
            self.indicator_poll_job = None
        if self.current_frame:
            self.current_frame.destroy()
        self.current_frame = tk.Frame(self.content, bg=self.colors['bg'])
        self.current_frame.pack(fill='both', expand=True)

    def sync_cloud(self):
        mac = get_mac_address_dash()
        try:
            push_report = sync_from_cloud(mac)
            print(f'[SYNC] mac_address used: {mac}')
            messagebox.showinfo(
                'Sync',
                'Cloud sync completed successfully.\n'
                f'Client ID: {CLIENT_ID}\n'
                f'MAC: {mac}\n'
                f"Running Logs Sent: {push_report.get('sent', 0)}/{push_report.get('total', 0)}\n"
                f"Failed: {push_report.get('failed', 0)}\n"
                f"Skipped: {push_report.get('skipped', 0)}",
            )
        except Exception as exc:
            print(f'[SYNC ERROR] mac_address used: {mac}')
            print(f'[SYNC ERROR] {exc}')
            messagebox.showerror('Sync Failed', f'{exc}\n\nMAC: {mac}')

    def show_home(self):
        self.clear_content()
        top = self._section_title(self.current_frame, 'Grinding & Stock Dashboard', '7-inch optimized view')
        tk.Label(top, text='Date:', bg=self.colors['bg'], fg=self.colors['muted'], font=('Segoe UI', 10, 'bold')).pack(side='left', padx=(28, 6))
        self.home_date = tk.StringVar(value=now_date())
        tk.Entry(top, textvariable=self.home_date, width=12, font=('Segoe UI', 11)).pack(side='left')
        tk.Button(
            top,
            text='Refresh',
            command=self.refresh_home,
            bg=self.colors['accent'],
            fg='white',
            relief='flat',
            padx=10,
            font=('Segoe UI', 10, 'bold'),
            cursor='hand2',
        ).pack(side='left', padx=8)
        self.home_total_var = tk.StringVar(value='Total Grinding: 0')
        tk.Label(top, textvariable=self.home_total_var, bg=self.colors['bg'], fg=self.colors['accent'], font=('Segoe UI', 12, 'bold')).pack(side='right')

        body = tk.Frame(self.current_frame, bg=self.colors['bg'])
        body.pack(fill='both', expand=True, padx=10, pady=6)

        top_row = tk.Frame(body, bg=self.colors['bg'])
        top_row.pack(fill='x')

        overview_card = tk.Frame(top_row, bg=self.colors['surface'], bd=0, highlightthickness=1, highlightbackground='#d7e2f0')
        overview_card.pack(side='left', fill='both', expand=True, padx=(0, 6), pady=6)
        tk.Label(overview_card, text='Grinding Overview', bg=self.colors['surface'], fg=self.colors['title'], font=('Segoe UI', 12, 'bold')).pack(anchor='w', padx=10, pady=(8, 2))
        self.overview_tree = ttk.Treeview(overview_card, columns=('shead', 'tons'), show='headings', height=5)
        self.overview_tree.heading('shead', text='Shead')
        self.overview_tree.heading('tons', text='Tons')
        self.overview_tree.column('shead', width=220, anchor='w')
        self.overview_tree.column('tons', width=100, anchor='center')
        self.overview_tree.pack(fill='x', padx=10, pady=(4, 10))

        summary_card = tk.Frame(top_row, bg=self.colors['surface'], bd=0, highlightthickness=1, highlightbackground='#d7e2f0')
        summary_card.pack(side='right', fill='both', expand=True, padx=(6, 0), pady=6)
        tk.Label(summary_card, text='Summary', bg=self.colors['surface'], fg=self.colors['title'], font=('Segoe UI', 12, 'bold')).pack(anchor='w', padx=10, pady=(8, 6))
        self.home_shead_var = tk.StringVar(value='Total Sheads: 0')
        self.home_date_var = tk.StringVar(value=f'Date: {self.home_date.get()}')
        tk.Label(summary_card, textvariable=self.home_total_var, bg=self.colors['surface'], fg=self.colors['accent'], font=('Segoe UI', 12, 'bold')).pack(anchor='w', padx=10, pady=2)
        tk.Label(summary_card, textvariable=self.home_shead_var, bg=self.colors['surface'], fg=self.colors['title'], font=('Segoe UI', 11)).pack(anchor='w', padx=10, pady=2)
        tk.Label(summary_card, textvariable=self.home_date_var, bg=self.colors['surface'], fg=self.colors['muted'], font=('Segoe UI', 10)).pack(anchor='w', padx=10, pady=(2, 10))

        lists = tk.Frame(body, bg=self.colors['bg'])
        lists.pack(fill='both', expand=True)

        left_card = tk.Frame(lists, bg=self.colors['surface'], bd=0, highlightthickness=1, highlightbackground='#d7e2f0')
        right_card = tk.Frame(lists, bg=self.colors['surface'], bd=0, highlightthickness=1, highlightbackground='#d7e2f0')
        left_card.pack(side='left', fill='both', expand=True, padx=(0, 6), pady=6)
        right_card.pack(side='right', fill='both', expand=True, padx=(6, 0), pady=6)

        tk.Label(left_card, text='Raw Materials', bg=self.colors['surface'], fg=self.colors['title'], font=('Segoe UI', 12, 'bold')).pack(anchor='w', padx=10, pady=(8, 2))
        raw_wrap = tk.Frame(left_card, bg=self.colors['surface'])
        raw_wrap.pack(fill='both', expand=True, padx=10, pady=(4, 10))
        raw_scroll = ttk.Scrollbar(raw_wrap, orient='vertical')
        self.raw_tree = ttk.Treeview(
            raw_wrap,
            columns=('sl', 'name', 'stock', 'unit', 'type'),
            show='headings',
            height=11,
            yscrollcommand=raw_scroll.set,
        )
        raw_scroll.config(command=self.raw_tree.yview)
        for c in ('sl', 'name', 'stock', 'unit', 'type'):
            self.raw_tree.heading(c, text=c.capitalize())
        self.raw_tree.column('sl', width=44, anchor='center')
        self.raw_tree.column('name', width=180, anchor='w')
        self.raw_tree.column('stock', width=88, anchor='e')
        self.raw_tree.column('unit', width=65, anchor='center')
        self.raw_tree.column('type', width=110, anchor='center')
        self.raw_tree.grid(row=0, column=0, sticky='nsew')
        raw_scroll.grid(row=0, column=1, sticky='ns')
        raw_wrap.grid_rowconfigure(0, weight=1)
        raw_wrap.grid_columnconfigure(0, weight=1)

        tk.Label(right_card, text='Feed / Medicine', bg=self.colors['surface'], fg=self.colors['title'], font=('Segoe UI', 12, 'bold')).pack(anchor='w', padx=10, pady=(8, 2))
        med_wrap = tk.Frame(right_card, bg=self.colors['surface'])
        med_wrap.pack(fill='both', expand=True, padx=10, pady=(4, 10))
        med_scroll = ttk.Scrollbar(med_wrap, orient='vertical')
        self.med_tree = ttk.Treeview(
            med_wrap,
            columns=('sl', 'name', 'stock', 'unit', 'type'),
            show='headings',
            height=11,
            yscrollcommand=med_scroll.set,
        )
        med_scroll.config(command=self.med_tree.yview)
        for c in ('sl', 'name', 'stock', 'unit', 'type'):
            self.med_tree.heading(c, text=c.capitalize())
        self.med_tree.column('sl', width=44, anchor='center')
        self.med_tree.column('name', width=180, anchor='w')
        self.med_tree.column('stock', width=88, anchor='e')
        self.med_tree.column('unit', width=65, anchor='center')
        self.med_tree.column('type', width=110, anchor='center')
        self.med_tree.grid(row=0, column=0, sticky='nsew')
        med_scroll.grid(row=0, column=1, sticky='ns')
        med_wrap.grid_rowconfigure(0, weight=1)
        med_wrap.grid_columnconfigure(0, weight=1)

        self.refresh_home()

    def refresh_home(self):
        try:
            counts, raw, med = get_dashboard_data(self.home_date.get())

            for i in self.overview_tree.get_children():
                self.overview_tree.delete(i)
            for name, val in sorted(counts.items()):
                self.overview_tree.insert('', tk.END, values=(name, val))

            self.home_total_var.set(f'Total Grinding: {sum(counts.values())}')
            self.home_shead_var.set(f'Total Sheads: {len(counts)}')
            self.home_date_var.set(f'Date: {self.home_date.get()}')

            for t in (self.raw_tree, self.med_tree):
                for i in t.get_children():
                    t.delete(i)

            for idx, r in enumerate(raw, start=1):
                self.raw_tree.insert(
                    '',
                    tk.END,
                    values=(idx, r.get('name'), r.get('stock'), r.get('metrics') or r.get('metric'), r.get('type')),
                )
            for idx, r in enumerate(med, start=1):
                self.med_tree.insert(
                    '',
                    tk.END,
                    values=(idx, r.get('name'), r.get('stock'), r.get('metrics') or r.get('metric'), r.get('type')),
                )
        except Exception as exc:
            messagebox.showerror('Home', str(exc))

    def show_configuration(self):
        self.clear_content()
        self._section_title(self.current_frame, 'Configuration', 'Manage sheads and motors')

        wrapper = tk.Frame(self.current_frame, bg=self.colors['bg'])
        wrapper.pack(fill='both', expand=True, padx=12, pady=(0, 8))

        left = tk.LabelFrame(wrapper, text='Create Sheads, Chicks & Growers', padx=12, pady=12, bg=self.colors['surface'])
        left.pack(side='left', fill='both', expand=True, padx=(0, 10))

        self.shead_count = tk.IntVar(value=0)
        self.chick_count = tk.IntVar(value=0)
        self.grower_count = tk.IntVar(value=0)

        self._labeled_spin(left, 'Number of Sheads', self.shead_count)
        self._labeled_spin(left, 'Number of Chicks', self.chick_count)
        self._labeled_spin(left, 'Number of Growers', self.grower_count)

        tk.Button(left, text='Save Shead Config', command=self.save_shead_config, bg=self.colors['accent'], fg='white', relief='flat', padx=12, pady=6, font=('Segoe UI', 10, 'bold')).pack(anchor='w', pady=8)

        right = tk.LabelFrame(wrapper, text='Motor Configuration', padx=12, pady=12, bg=self.colors['surface'])
        right.pack(side='right', fill='both', expand=True, padx=(10, 0))

        self.motor_count = tk.IntVar(value=1)
        self._labeled_spin(right, 'How many motors?', self.motor_count, minval=1, maxval=20)
        tk.Button(right, text='Generate Motor Material Selectors', command=self.generate_motor_selectors, bg='#2d6cdf', fg='white', relief='flat', padx=10, pady=6, font=('Segoe UI', 10, 'bold')).pack(anchor='w', pady=8)

        self.motor_select_frame = tk.Frame(right, bg=self.colors['surface'])
        self.motor_select_frame.pack(fill='both', expand=True)

        tk.Button(right, text='Save Motor Config', command=self.save_motor_configuration, bg=self.colors['accent'], fg='white', relief='flat', padx=12, pady=6, font=('Segoe UI', 10, 'bold')).pack(anchor='w', pady=8)

        table_card = self._card(self.current_frame, padx=12, pady=(0, 10))
        tk.Label(table_card, text='Current Motor Mapping', bg=self.colors['surface'], fg=self.colors['title'], font=('Segoe UI', 12, 'bold')).pack(anchor='w', padx=10, pady=(8, 4))
        monitor_wrap = tk.Frame(table_card, bg=self.colors['surface'])
        monitor_wrap.pack(fill='x', padx=10, pady=(0, 10))

        left_sec = tk.Frame(monitor_wrap, bg=self.colors['surface'], bd=0, highlightthickness=1, highlightbackground='#d7e2f0')
        right_sec = tk.Frame(monitor_wrap, bg=self.colors['surface'], bd=0, highlightthickness=1, highlightbackground='#d7e2f0')
        left_sec.pack(side='left', fill='both', expand=True, padx=(0, 6))
        right_sec.pack(side='right', fill='both', expand=True, padx=(6, 0))

        tk.Label(left_sec, text='Section A', bg=self.colors['surface'], fg=self.colors['title'], font=('Segoe UI', 11, 'bold')).pack(anchor='w', padx=8, pady=(6, 2))
        tk.Label(right_sec, text='Section B', bg=self.colors['surface'], fg=self.colors['title'], font=('Segoe UI', 11, 'bold')).pack(anchor='w', padx=8, pady=(6, 2))

        self.motor_table_left = ttk.Treeview(
            left_sec,
            columns=('motor', 'material'),
            show='headings',
            height=6,
        )
        self.motor_table_right = ttk.Treeview(
            right_sec,
            columns=('motor', 'material'),
            show='headings',
            height=6,
        )
        for t in (self.motor_table_left, self.motor_table_right):
            t.heading('motor', text='Motor')
            t.heading('material', text='Material')
            t.column('motor', width=90, anchor='center')
            t.column('material', width=170, anchor='w')
            t.pack(fill='x', padx=8, pady=(2, 8))

        self.generate_motor_selectors()
        self.refresh_motor_table()

    def _labeled_spin(self, parent, label, variable, minval=0, maxval=500):
        row = tk.Frame(parent, bg=self.colors['surface'])
        row.pack(fill='x', pady=4)
        tk.Label(row, text=label, width=24, anchor='w', bg=self.colors['surface'], fg=self.colors['muted'], font=('Segoe UI', 10, 'bold')).pack(side='left')
        tk.Spinbox(row, from_=minval, to=maxval, textvariable=variable, width=8, font=('Segoe UI', 10)).pack(side='left')

    def save_shead_config(self):
        try:
            update_shead_counts(self.shead_count.get(), self.chick_count.get(), self.grower_count.get())
            messagebox.showinfo('Configuration', 'Shead/chick/grower config updated.')
        except Exception as exc:
            messagebox.showerror('Configuration', str(exc))

    def generate_motor_selectors(self):
        for child in self.motor_select_frame.winfo_children():
            child.destroy()
        self.motor_material_vars = []

        raw_materials = get_material_options()
        if not raw_materials:
            raw_materials = ['']
            messagebox.showwarning('Motor Config', 'No materials found in feed_rawmaterial table.')

        for i in range(1, self.motor_count.get() + 1):
            row = tk.Frame(self.motor_select_frame, bg=self.colors['surface'])
            row.pack(fill='x', pady=3)
            tk.Label(row, text=f'Motor {i}', width=12, anchor='w', bg=self.colors['surface'], fg=self.colors['muted'], font=('Segoe UI', 10, 'bold')).pack(side='left')
            var = tk.StringVar(value=raw_materials[0])
            tk.OptionMenu(row, var, *raw_materials).pack(side='left', fill='x', expand=True)
            self.motor_material_vars.append(var)

    def save_motor_configuration(self):
        try:
            materials = [v.get().strip() for v in self.motor_material_vars if v.get().strip()]
            if len(materials) != self.motor_count.get():
                messagebox.showwarning('Motor Config', 'Please select material for each motor.')
                return
            save_motor_config(materials)
            self.refresh_motor_table()
            messagebox.showinfo('Motor Config', 'Motor configuration saved.')
        except Exception as exc:
            messagebox.showerror('Motor Config', str(exc))

    def refresh_motor_table(self):
        for i in self.motor_table_left.get_children():
            self.motor_table_left.delete(i)
        for i in self.motor_table_right.get_children():
            self.motor_table_right.delete(i)

        rows = get_motor_config()
        mid = (len(rows) + 1) // 2
        left_rows = rows[:mid]
        right_rows = rows[mid:]

        for row in left_rows:
            self.motor_table_left.insert('', tk.END, values=(row['motor_number'], row['material_name']))
        for row in right_rows:
            self.motor_table_right.insert('', tk.END, values=(row['motor_number'], row['material_name']))

    def show_feed_formula(self):
        self.clear_content()

        header = self._section_title(self.current_frame, 'Feed Formula Overview', 'Double click any value to edit')
        tk.Button(header, text='Refresh', command=self.refresh_formula, bg='#2d6cdf', fg='white', relief='flat', padx=10, font=('Segoe UI', 10, 'bold')).pack(side='right')

        control = tk.Frame(self.current_frame, bg=self.colors['bg'])
        control.pack(fill='x', padx=14, pady=4)
        tk.Button(control, text='Save Edited Values', command=self.save_formula_changes, bg=self.colors['accent'], fg='white', relief='flat', padx=10, font=('Segoe UI', 10, 'bold')).pack(side='left')
        tk.Button(control, text='Add New Material', command=self.add_material_popup, bg='#145a32', fg='white', relief='flat', padx=10, font=('Segoe UI', 10, 'bold')).pack(side='left', padx=8)
        self.formula_status = tk.StringVar(value='Loading formula...')
        tk.Label(control, textvariable=self.formula_status, bg=self.colors['bg'], fg='#1f618d', font=('Segoe UI', 10, 'bold')).pack(side='right')

        table_card = self._card(self.current_frame, padx=14, pady=8)
        ttk.Style().configure('Formula.Treeview', rowheight=36, font=('Segoe UI', 11))
        ttk.Style().configure('Formula.Treeview.Heading', font=('Segoe UI', 11, 'bold'))

        table_wrap = tk.Frame(table_card, bg=self.colors['surface'])
        table_wrap.pack(fill='both', expand=True, padx=8, pady=8)

        yscroll = ttk.Scrollbar(table_wrap, orient='vertical')
        self.formula_tree = ttk.Treeview(
            table_wrap,
            show='headings',
            style='Formula.Treeview',
            yscrollcommand=yscroll.set,
        )
        yscroll.config(command=self.formula_tree.yview)

        self.formula_tree.grid(row=0, column=0, sticky='nsew')
        yscroll.grid(row=0, column=1, sticky='ns')
        table_wrap.grid_rowconfigure(0, weight=1)
        table_wrap.grid_columnconfigure(0, weight=1)

        self.formula_tree.tag_configure('odd', background='#b5dbef')
        self.formula_tree.tag_configure('even', background='#c4e4f4')
        self.formula_tree.bind('<Double-1>', self.edit_formula_cell)

        self.refresh_formula()

    def _build_formula_rows(self):
        sheads = [list(item.keys())[0] for item in self.formula_data]
        types = ['Feed_Formula']
        rows = []
        for t in types:
            materials = set()
            for item in self.formula_data:
                s = list(item.keys())[0]
                materials.update((item[s].get(t) or {}).keys())
            for m in sorted(materials):
                row = {'material': m}
                for item in self.formula_data:
                    s = list(item.keys())[0]
                    val = (item[s].get(t) or {}).get(m, 0)
                    row[s] = val
                rows.append(row)
        return sheads, rows

    def refresh_formula(self):
        try:
            self.formula_data = get_feed_formula_structured()
            sheads, rows = self._build_formula_rows()

            cols = ['material'] + sheads
            self.formula_tree['columns'] = cols
            tree_width = self.formula_tree.winfo_width()
            if tree_width <= 1:
                tree_width = max(self.root.winfo_width() - 280, 680)
            material_w = 180
            shead_count = max(len(sheads), 1)
            shead_w = max(80, int((tree_width - material_w - 24) / shead_count))
            for c in cols:
                label = c.replace('_', ' ').upper()
                self.formula_tree.heading(c, text=label)
                if c == 'material':
                    self.formula_tree.column(c, width=material_w, stretch=False, anchor='w')
                else:
                    self.formula_tree.column(c, width=shead_w, stretch=True, anchor='center')

            for i in self.formula_tree.get_children():
                self.formula_tree.delete(i)

            for idx, row in enumerate(rows):
                tag = 'even' if idx % 2 == 0 else 'odd'
                self.formula_tree.insert('', tk.END, values=[row.get(c, '') for c in cols], tags=(tag,))
            if self.formula_status is not None:
                self.formula_status.set(
                    f'Loaded: {len(sheads)} sheads, {len(rows)} rows'
                )
            if not rows:
                messagebox.showinfo(
                    'Feed Formula',
                    'No formula rows found. Please sync or add materials.',
                )

        except Exception as exc:
            messagebox.showerror('Feed Formula', str(exc))

    def edit_formula_cell(self, event):
        self._commit_formula_editor()
        item_id = self.formula_tree.identify_row(event.y)
        col_id = self.formula_tree.identify_column(event.x)
        if not item_id or col_id == '#1':
            return

        x, y, w, h = self.formula_tree.bbox(item_id, col_id)
        old_value = self.formula_tree.set(item_id, col_id)

        entry = tk.Entry(self.formula_tree)
        entry.place(x=x, y=y, width=w, height=h)
        entry.insert(0, old_value)
        entry.focus()
        self.formula_editor = entry
        self.formula_editor_item = item_id
        self.formula_editor_col = col_id

        def save_edit(_evt=None):
            if entry.winfo_exists():
                self.formula_tree.set(item_id, col_id, entry.get().strip() or '0')
                entry.destroy()
            self.formula_editor = None
            self.formula_editor_item = None
            self.formula_editor_col = None

        entry.bind('<Return>', save_edit)
        entry.bind('<FocusOut>', save_edit)
        entry.bind('<Escape>', lambda _evt=None: (entry.destroy(), setattr(self, 'formula_editor', None)))

    def _commit_formula_editor(self):
        if self.formula_editor is not None and self.formula_editor.winfo_exists():
            value = self.formula_editor.get().strip() or '0'
            if self.formula_editor_item and self.formula_editor_col:
                self.formula_tree.set(self.formula_editor_item, self.formula_editor_col, value)
            self.formula_editor.destroy()
        self.formula_editor = None
        self.formula_editor_item = None
        self.formula_editor_col = None

    def save_formula_changes(self):
        try:
            # Ensure active inline cell editor is committed before reading tree values.
            self._commit_formula_editor()
            self.root.update_idletasks()

            cols = list(self.formula_tree['columns'])
            sheads = cols[1:]

            staged = {s: {'Feed_Formula': {}} for s in sheads}
            for item_id in self.formula_tree.get_children():
                vals = self.formula_tree.item(item_id, 'values')
                material = vals[0]
                row_type = 'Feed_Formula'
                for idx, s in enumerate(sheads, start=1):
                    try:
                        qty = float(vals[idx])
                    except Exception:
                        qty = 0
                    staged[s][row_type][material] = qty

            payload = [{s: staged[s]} for s in sheads]
            upsert_formula(payload)
            messagebox.showinfo('Feed Formula', 'Formula updated successfully.')
            self.refresh_formula()
        except Exception as exc:
            messagebox.showerror('Feed Formula', str(exc))

    def add_material_popup(self):
        popup = tk.Toplevel(self.root)
        popup.title('Add New Material')
        popup.geometry('380x200')

        tk.Label(popup, text='Type').pack(anchor='w', padx=12, pady=(12, 4))
        type_var = tk.StringVar(value='Feed_Formula')
        tk.OptionMenu(popup, type_var, 'Feed_Formula').pack(fill='x', padx=12)

        tk.Label(popup, text='Material').pack(anchor='w', padx=12, pady=(10, 4))
        # Feed Formula page should only use raw materials.
        all_materials = [
            x['name']
            for x in fetchall(
                "SELECT name FROM feed_rawmaterial WHERE client_id=%s AND LOWER(type)='raw material' ORDER BY name",
                (CLIENT_ID,),
            )
        ]
        if not all_materials:
            all_materials = ['']
        mat_var = tk.StringVar(value=all_materials[0] if all_materials else '')
        tk.OptionMenu(popup, mat_var, *all_materials).pack(fill='x', padx=12)

        def on_add():
            try:
                if not mat_var.get().strip():
                    messagebox.showwarning('Material', 'Select material.')
                    return
                add_new_material(mat_var.get().strip(), type_var.get())
                popup.destroy()
                self.refresh_formula()
                messagebox.showinfo('Material', 'Material added successfully.')
            except Exception as exc:
                messagebox.showerror('Material', str(exc))

        tk.Button(popup, text='Add Material', command=on_add).pack(pady=14)

    def show_report(self):
        self.clear_content()

        self._section_title(self.current_frame, 'Reports', 'Production and consumption summary')

        filter_card = self._card(self.current_frame, padx=14, pady=(0, 8))
        filter_row = tk.Frame(filter_card, bg=self.colors['surface'])
        filter_row.pack(fill='x', padx=10, pady=10)

        self.filter_var = tk.StringVar(value='today')
        self.shead_var = tk.StringVar(value='All')
        self.from_var = tk.StringVar(value=now_date())
        self.to_var = tk.StringVar(value=now_date())

        tk.Label(filter_row, text='Range', bg=self.colors['surface'], fg=self.colors['muted'], font=('Segoe UI', 10, 'bold')).pack(side='left', padx=(0, 6))
        range_menu = tk.OptionMenu(filter_row, self.filter_var, 'today', 'yesterday', 'weekly', 'monthly', 'yearly', 'custom')
        range_menu.pack(side='left', padx=(0, 12))

        sheads = ['All'] + [x['shead_name'] for x in get_sheads()]
        if not sheads:
            sheads = ['All']
        tk.Label(filter_row, text='Shead', bg=self.colors['surface'], fg=self.colors['muted'], font=('Segoe UI', 10, 'bold')).pack(side='left', padx=(0, 6))
        tk.OptionMenu(filter_row, self.shead_var, *sheads).pack(side='left', padx=(0, 12))

        custom_date_frame = tk.Frame(filter_row, bg=self.colors['surface'])
        from_lbl = tk.Label(custom_date_frame, text='From', bg=self.colors['surface'], fg=self.colors['muted'], font=('Segoe UI', 10, 'bold'))
        from_entry = tk.Entry(custom_date_frame, textvariable=self.from_var, width=12, font=('Segoe UI', 10))
        to_lbl = tk.Label(custom_date_frame, text='To', bg=self.colors['surface'], fg=self.colors['muted'], font=('Segoe UI', 10, 'bold'))
        to_entry = tk.Entry(custom_date_frame, textvariable=self.to_var, width=12, font=('Segoe UI', 10))
        from_lbl.pack(side='left', padx=(0, 6))
        from_entry.pack(side='left', padx=(0, 8))
        to_lbl.pack(side='left', padx=(0, 6))
        to_entry.pack(side='left', padx=(0, 10))

        load_btn = tk.Button(
            filter_row,
            text='Load Report',
            command=self.refresh_report,
            bg=self.colors['accent'],
            fg='white',
            relief='flat',
            padx=10,
            font=('Segoe UI', 10, 'bold'),
        )

        def toggle_custom_dates(*_args):
            if self.filter_var.get() == 'custom':
                if not custom_date_frame.winfo_ismapped():
                    custom_date_frame.pack(side='left', padx=(0, 6))
            else:
                custom_date_frame.pack_forget()
            # Keep button order consistent (always after date fields).
            load_btn.pack_forget()
            load_btn.pack(side='left')

        self.filter_var.trace_add('write', toggle_custom_dates)
        load_btn.pack(side='left')
        toggle_custom_dates()

        report_card = self._card(self.current_frame, padx=14, pady=8)
        self.report_text = tk.Text(
            report_card,
            bg=self.colors['surface'],
            fg='#102a43',
            font=('Consolas', 10),
            relief='flat',
            highlightthickness=1,
            highlightbackground='#8fb6d8',
        )
        self.report_text.pack(fill='both', expand=True, padx=10, pady=10)

        self.refresh_report()

    def refresh_report(self):
        try:
            shead_data, mat_data, materials = get_report(
                self.filter_var.get(),
                self.shead_var.get(),
                self.from_var.get(),
                self.to_var.get(),
            )
            self.report_text.delete('1.0', tk.END)
            self.report_text.insert(tk.END, 'Shead Grinding Summary\n')
            self.report_text.insert(tk.END, '----------------------\n')
            for date, rows in shead_data.items():
                self.report_text.insert(tk.END, f'{date}\n')
                for s, val in rows.items():
                    self.report_text.insert(tk.END, f'  {s}: {val}\n')

            self.report_text.insert(tk.END, '\nFeed Material Consumption\n')
            self.report_text.insert(tk.END, '--------------------------\n')
            for date, rows in mat_data.items():
                self.report_text.insert(tk.END, f'{date}\n')
                for m in materials:
                    if m in rows:
                        self.report_text.insert(tk.END, f'  {m}: {rows[m]}\n')
        except Exception as exc:
            messagebox.showerror('Report', str(exc))

    def show_auto_batching(self):
        self.clear_content()
        self.batch_view_active = True

        self._section_title(self.current_frame, 'Auto Batching', 'Live monitoring and control panel')
        card = self._card(self.current_frame, padx=14, pady=8)

        self.proc_status.set('Running' if self.batch_running else 'Stopped')
        self.proc_pid.set('Integrated')
        if not self.batch_running:
            self.current_batch_feed = None
            self.batch_current_var.set('Currently Running Material: None')
            self.batch_current_weight_var.set('Material Quantity: 0')
            self.batch_expected_var.set('Cumulative Expected Weight: 0')
            self.batch_indicator_var.set('Live Indicator: N/A')

        top_status = tk.Frame(card, bg=self.colors['surface'])
        top_status.pack(fill='x', padx=10, pady=(8, 4))
        tk.Label(top_status, text='Status:', bg=self.colors['surface'], fg=self.colors['muted'], font=('Segoe UI', 10, 'bold')).pack(side='left')
        tk.Label(top_status, textvariable=self.proc_status, bg=self.colors['surface'], fg=self.colors['title'], font=('Segoe UI', 10, 'bold')).pack(side='left', padx=(6, 20))
        tk.Label(top_status, text='Engine:', bg=self.colors['surface'], fg=self.colors['muted'], font=('Segoe UI', 10, 'bold')).pack(side='left')
        tk.Label(top_status, textvariable=self.proc_pid, bg=self.colors['surface'], fg=self.colors['title'], font=('Segoe UI', 10, 'bold')).pack(side='left', padx=(6, 0))

        controls = tk.Frame(card, bg=self.colors['surface'])
        controls.pack(fill='x', padx=10, pady=(8, 6))
        tk.Label(
            controls,
            text='Select Feed Type:',
            bg=self.colors['surface'],
            fg=self.colors['title'],
            font=('Segoe UI', 12, 'bold'),
        ).pack(side='left')

        feed_frame = tk.Frame(card, bg=self.colors['surface'])
        feed_frame.pack(fill='x', padx=10, pady=(0, 6))
        feed_types = get_batch_feed_types()
        self.batch_feed_buttons = []
        self.batch_feed_button_map = {}
        if not feed_types:
            tk.Label(feed_frame, text='No shead feed types found.', bg=self.colors['surface'], fg=self.colors['danger'], font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        else:
            for idx, feed in enumerate(feed_types):
                btn = tk.Button(
                    feed_frame,
                    text=feed,
                    command=lambda f=feed: self.start_batching(f),
                    bg='#1f6ed4',
                    fg='white',
                    relief='flat',
                    padx=12,
                    pady=6,
                    font=('Segoe UI', 10, 'bold'),
                )
                r = idx // 5
                c = idx % 5
                btn.grid(row=r, column=c, padx=4, pady=4, sticky='ew')
                self.batch_feed_buttons.append(btn)
                self.batch_feed_button_map[feed] = btn
            for c in range(5):
                feed_frame.grid_columnconfigure(c, weight=1)

        stop_btn = tk.Button(
            controls,
            text='STOP PROCESS',
            command=self.stop_batching,
            bg=self.colors['danger'],
            fg='white',
            relief='flat',
            padx=12,
            pady=6,
            font=('Segoe UI', 10, 'bold'),
        )
        stop_btn.pack(side='right')

        status_frame = tk.Frame(card, bg=self.colors['surface'], highlightthickness=1, highlightbackground='#8fb6d8')
        status_frame.pack(fill='x', padx=10, pady=(0, 6))
        tk.Label(status_frame, textvariable=self.batch_current_var, bg=self.colors['surface'], fg=self.colors['title'], font=('Segoe UI', 11, 'bold')).grid(row=0, column=0, padx=10, pady=6, sticky='w')
        tk.Label(status_frame, textvariable=self.batch_current_weight_var, bg=self.colors['surface'], fg=self.colors['title'], font=('Segoe UI', 11, 'bold')).grid(row=0, column=1, padx=10, pady=6, sticky='w')
        tk.Label(status_frame, textvariable=self.batch_expected_var, bg=self.colors['surface'], fg=self.colors['title'], font=('Segoe UI', 11, 'bold')).grid(row=0, column=2, padx=10, pady=6, sticky='w')
        status_frame.grid_columnconfigure(0, weight=1)
        status_frame.grid_columnconfigure(1, weight=1)
        status_frame.grid_columnconfigure(2, weight=1)

        tk.Label(
            card,
            textvariable=self.batch_indicator_var,
            bg=self.colors['surface'],
            fg='#0b3d2e',
            font=('Segoe UI', 27, 'bold'),
        ).pack(anchor='w', padx=10, pady=(0, 6))

        tk.Label(card, text='Motor vs Material Target', bg=self.colors['surface'], fg=self.colors['title'], font=('Segoe UI', 11, 'bold')).pack(anchor='w', padx=10, pady=(0, 4))
        self.batch_material_tree = ttk.Treeview(card, columns=('motor', 'material', 'quantity'), show='headings', height=8)
        self.batch_material_tree.heading('motor', text='Motor')
        self.batch_material_tree.heading('material', text='Material')
        self.batch_material_tree.heading('quantity', text='Target Qty')
        self.batch_material_tree.column('motor', width=90, anchor='center')
        self.batch_material_tree.column('material', width=280, anchor='w')
        self.batch_material_tree.column('quantity', width=120, anchor='center')
        self.batch_material_tree.pack(fill='x', padx=10, pady=(0, 6))
        self._populate_material_table(None)

        tk.Label(card, text='Process Logs:', bg=self.colors['surface'], fg=self.colors['title'], font=('Segoe UI', 11, 'bold')).pack(anchor='w', padx=10, pady=(0, 4))
        log_frame = tk.Frame(card, bg=self.colors['surface'])
        log_frame.pack(fill='both', expand=True, padx=10, pady=(0, 8))
        log_scroll = ttk.Scrollbar(log_frame, orient='vertical')
        self.batch_log_text = tk.Text(
            log_frame,
            height=7,
            bg='#111111',
            fg='#00FF9C',
            insertbackground='white',
            font=('Consolas', 10),
            yscrollcommand=log_scroll.set,
        )
        log_scroll.config(command=self.batch_log_text.yview)
        self.batch_log_text.grid(row=0, column=0, sticky='nsew')
        log_scroll.grid(row=0, column=1, sticky='ns')
        log_frame.grid_rowconfigure(0, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)

        if self.indicator_client is None:
            _relay, self.indicator_client = self._init_modbus_clients()
        self.refresh_proc_status()
        self._highlight_active_feed(self.current_batch_feed if self.batch_running else None)
        self._populate_material_table(self.current_batch_feed)
        if self.batch_running:
            self._set_feed_buttons_state('normal')
        self._batch_log('Auto batching panel ready.')
        self._start_indicator_polling()

    def _set_feed_buttons_state(self, state):
        for btn in self.batch_feed_buttons:
            try:
                btn.configure(state=state)
            except Exception:
                pass

    def _highlight_active_feed(self, active_feed=None):
        active_feed = (active_feed or '').strip()
        for feed_name, btn in self.batch_feed_button_map.items():
            try:
                if active_feed and feed_name == active_feed:
                    btn.configure(
                        bg='#0f5132',
                        fg='white',
                        activebackground='#0f5132',
                        activeforeground='white',
                    )
                else:
                    btn.configure(
                        bg='#8da6bf',
                        fg='#243447',
                        activebackground='#7890a8',
                        activeforeground='#243447',
                    )
            except Exception:
                pass

    def _populate_material_table(self, selected_feed=None):
        if self.batch_material_tree is None or not self.batch_material_tree.winfo_exists():
            return
        for item in self.batch_material_tree.get_children():
            self.batch_material_tree.delete(item)

        motors = get_motor_materials_for_batch()
        feed_key = (selected_feed or self.current_batch_feed or '').strip()
        formula = get_formula_for_feed(feed_key) if feed_key else {}
        for row in motors:
            motor_no = row.get('motor_number')
            material = row.get('material_name') or 'N/A'
            qty = float(formula.get(material, 0) or 0)
            self.batch_material_tree.insert('', tk.END, values=(motor_no, material, int(qty) if qty.is_integer() else round(qty, 2)))

    def _start_indicator_polling(self):
        if not (self.batch_view_active or self.batch_running):
            return
        if self.indicator_poll_job is not None:
            try:
                self.root.after_cancel(self.indicator_poll_job)
            except Exception:
                pass
            self.indicator_poll_job = None
        self.indicator_poll_job = self.root.after(50, self._poll_indicator_continuous)

    def _poll_indicator_continuous(self):
        if not (self.batch_view_active or self.batch_running):
            self.indicator_poll_job = None
            return

        indicator = self._read_indicator()
        if indicator is not None:
            self.batch_indicator_var.set(f'Live Indicator: {indicator}')
        else:
            self.batch_indicator_var.set('Live Indicator: N/A')
        self.indicator_poll_job = self.root.after(50, self._poll_indicator_continuous)

    def _batch_log(self, message):
        stamp = datetime.now().strftime('%H:%M:%S')
        line = f'[{stamp}] {message}\n'
        print(f'[BATCH] {message}')
        if self.batch_log_text is not None and self.batch_log_text.winfo_exists():
            self.batch_log_text.insert(tk.END, line)
            self.batch_log_text.see(tk.END)

    def _init_modbus_clients(self):
        if ModbusSerialClient is None:
            self._batch_log('pymodbus not installed. Running in simulation mode.')
            return None, None
        try:
            relay = ModbusSerialClient(
                method='rtu',
                port='/dev/ttyACM0',
                baudrate=9600,
                parity='N',
                stopbits=1,
                bytesize=8,
                timeout=1,
            )
            indicator = ModbusSerialClient(
                method='rtu',
                port='/dev/ttyACM0',
                baudrate=9600,
                parity='N',
                stopbits=1,
                bytesize=8,
                timeout=1,
            )
            return relay, indicator
        except Exception as exc:
            self._batch_log(f'Hardware init failed: {exc}. Using simulation mode.')
            return None, None

    def _read_indicator(self):
        if self.indicator_client is None:
            return None
        with self.modbus_lock:
            for _ in range(3):
                try:
                    if self.indicator_client.connect():
                        result = self.indicator_client.read_holding_registers(address=0, count=1, unit=2)
                        self.indicator_client.close()
                        if result.isError():
                            time.sleep(0.005)
                            continue
                        value = int(result.registers[0])
                        value = 0 if value > 5000 else value
                        self.last_indicator_value = value
                        self.last_indicator_ts = time.time()
                        return value
                except Exception:
                    time.sleep(0.005)
                    continue
        return None

    def _write_relay(self, coil, state, attempts=3, retry_delay=0.03):
        if self.relay_client is None:
            return True
        for _ in range(max(1, attempts)):
            with self.modbus_lock:
                try:
                    if self.relay_client.connect():
                        res = self.relay_client.write_coil(coil, bool(state), unit=1)
                        self.relay_client.close()
                        if not res.isError():
                            return True
                except Exception:
                    pass
            time.sleep(retry_delay)
        return False

    def _stop_all_relays(self):
        motors = get_motor_materials_for_batch()
        for idx, _row in enumerate(motors):
            ok = self._write_relay(idx, False, attempts=5, retry_delay=0.05)
            if not ok:
                self._batch_log(f'Warning: failed to switch OFF relay {idx + 1}')

    def _run_batching_worker(self, selected_feed):
        self.batch_running = True
        self.current_batch_feed = selected_feed
        self.root.after(0, self.refresh_proc_status)
        self.root.after(0, lambda: self._highlight_active_feed(selected_feed))
        self.root.after(0, lambda f=selected_feed: self._populate_material_table(f))
        self._batch_log(f'Started integrated batching for: {selected_feed}')
        self.relay_client, self.indicator_client = self._init_modbus_clients()
        simulation_mode = self.indicator_client is None
        try:
            motors = get_motor_materials_for_batch()
            if not motors:
                self._batch_log('No motor configuration found.')
                return

            formula = get_formula_for_feed(selected_feed)
            if not formula:
                self._batch_log('No feed formula found for selected shead.')
                return

            cumulative = 0
            for idx, row in enumerate(motors):
                if self.batch_stop_event.is_set():
                    self._batch_log('Stop requested. Ending run...')
                    break

                material = row.get('material_name')
                qty = int(float(formula.get(material, 0)))
                cumulative += qty
                self.root.after(0, lambda m=material: self.batch_current_var.set(f'Current Material: {m}'))
                self.root.after(0, lambda q=qty: self.batch_current_weight_var.set(f'Material Quantity: {q}'))
                self.root.after(0, lambda c=cumulative: self.batch_expected_var.set(f'Expected Cumulative: {c}'))
                self._batch_log(f'Material={material}, Qty={qty}, Cumulative={cumulative}')

                if qty <= 0:
                    continue

                if not self._write_relay(idx, True, attempts=4, retry_delay=0.04):
                    self._batch_log(f'Failed to switch ON relay {idx + 1} for {material}, skipping.')
                    continue
                started = time.time()
                matched = False
                while not self.batch_stop_event.is_set():
                    indicator = self.last_indicator_value
                    if indicator is None:
                        # Only auto-advance quickly in explicit simulation mode.
                        if simulation_mode and (time.time() - started > 2):
                            matched = True
                            break
                        # Real hardware transient read miss: keep waiting until per-material timeout.
                        if (not simulation_mode) and (time.time() - started > 180):
                            self._batch_log(f'Indicator read timeout for {material}, moving to next material.')
                            break
                        time.sleep(0.02)
                        continue
                    if indicator >= cumulative:
                        matched = True
                        break
                    if time.time() - started > 180:
                        self._batch_log('Indicator timeout reached, moving to next material.')
                        break
                    time.sleep(0.02)

                if not self._write_relay(idx, False, attempts=6, retry_delay=0.05):
                    self._batch_log(f'Critical: relay {idx + 1} OFF failed, forcing all relays OFF.')
                    self._stop_all_relays()
                if matched:
                    self._batch_log(f'Match reached for {material}')
                if (idx < len(motors) - 1) and (not self.batch_stop_event.is_set()):
                    self._batch_log('Waiting 2.5 seconds before next relay...')
                    pause_until = time.time() + 2.5
                    while time.time() < pause_until and not self.batch_stop_event.is_set():
                        time.sleep(0.1)

            if not self.batch_stop_event.is_set():
                insert_running_log(selected_feed)
                self._batch_log('Batching completed and running log inserted.')
        except Exception as exc:
            self._batch_log(f'Batching error: {exc}')
            traceback.print_exc()
        finally:
            self._stop_all_relays()
            self.batch_running = False
            self.current_batch_feed = None
            self.root.after(0, lambda: self._highlight_active_feed(None))
            self.root.after(0, lambda: self._set_feed_buttons_state('normal'))
            self.root.after(0, lambda: self.batch_current_var.set('Currently Running Material: None'))
            self.root.after(0, lambda: self.batch_current_weight_var.set('Material Quantity: 0'))
            self.root.after(0, self.refresh_proc_status)

    def start_batching(self, selected_feed=None):
        try:
            if self.batch_running:
                messagebox.showinfo('Auto Batching', 'Auto batching is already running.')
                return
            selected_feed = (selected_feed or '').strip()
            if not selected_feed:
                messagebox.showwarning('Auto Batching', 'Please select a feed type.')
                return
            self.current_batch_feed = selected_feed
            self._populate_material_table(selected_feed)
            self._highlight_active_feed(selected_feed)
            self.batch_stop_event.clear()
            self.batch_thread = threading.Thread(
                target=self._run_batching_worker,
                args=(selected_feed,),
                daemon=True,
            )
            self.batch_thread.start()
            self.refresh_proc_status()
            messagebox.showinfo('Auto Batching', 'Started successfully.')
        except Exception as exc:
            messagebox.showerror('Auto Batching', str(exc))

    def stop_batching(self):
        try:
            if not self.batch_running:
                messagebox.showinfo('Auto Batching', 'Process is not running.')
                self.refresh_proc_status()
                return
            self.batch_stop_event.set()
            self._stop_all_relays()
            self._batch_log('Stop requested by user.')
            self.refresh_proc_status()
            self._highlight_active_feed(self.current_batch_feed)
        except Exception as exc:
            messagebox.showerror('Auto Batching', str(exc))

    def refresh_proc_status(self):
        if self.batch_running:
            self.proc_status.set('Running')
            self.proc_pid.set('Integrated')
        else:
            self.proc_status.set('Stopped')
            self.proc_pid.set('Integrated')

    def run(self):
        self.root.mainloop()


def main():
    restart_apache()
    app = AutoBatchingDesktop()
    app.run()


if __name__ == '__main__':
    main()
