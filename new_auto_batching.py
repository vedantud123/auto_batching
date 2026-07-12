import csv
import serial
import time
import re
import tkinter as tk
from tkinter import ttk
import logging
from datetime import datetime
import pytz
import pandas as pd
import requests
import urllib.parse
import os
from pymodbus.client.sync import ModbusSerialClient
import time
from pymodbus.client.sync import ModbusSerialClient as ModbusClient
import ttkbootstrap as tb
from ttkbootstrap.constants import *
import subprocess
import mysql.connector

def start_apache():
    try:
        subprocess.run(
            ["sudo", "systemctl", "start", "apache2"],
            check=True
        )
        print("Apache started successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Failed to start Apache: {e}")

start_apache()

DB_HOST = "localhost"
DB_USER = "root"
DB_PASS = "sunfra"
DB_NAME = "auto_batching"

def get_db_connection():
    try:
        conn = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASS,
            database=DB_NAME
        )
        print("Database Connected Successfully")
        return conn
    except mysql.connector.Error as err:
        print(f"Database Connection Error: {err}")
        return None

conn = get_db_connection()

if conn:
    cursor = conn.cursor(dictionary=True)

PORT="/dev/ttyACM0"
BAUDRATE = 9600
PARITY = 'N'
STOPBITS = 1
BYTESIZE = 8
TIMEOUT = 1
SLAVE_ID = 1
COIL_ADDRESS = 4  

client = ModbusSerialClient(
    method='rtu',
    port=PORT,
    baudrate=BAUDRATE,
    parity=PARITY,
    stopbits=STOPBITS,
    bytesize=BYTESIZE,
    timeout=TIMEOUT
)

client2 = ModbusClient(
    method='rtu',
    port='/dev/ttyACM0',
    baudrate=9600,  
    timeout=1,
    stopbits=1,
    bytesize=8,
    parity='N'
)


logging.basicConfig(filename='/home/sunfra/Documents/my_script.log', level=logging.DEBUG)
logging.info('Script started successfully!')

CSV_FILE = "/home/sunfra/Documents/script_log.csv"  

def load_motor_pins():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    query = """
    SELECT motor_number, material_name
    FROM motor_config
    ORDER BY motor_number
    """

    cursor.execute(query)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    pins = {}
    for index, row in enumerate(rows):
        motor_no = row["motor_number"]
        pins[motor_no] = index   
    print("Motor Pins Loaded:", pins)
    return pins

pins = load_motor_pins()

ser = None
try:
    ser = serial.Serial('/dev/ttyS0', 9600, timeout=1)
    ser.flush()
except serial.SerialException as e:
    logging.error(f"Serial port error: {e}")
    ser = None

root = tb.Window(themename="darkly")  
root.title("Feed Automation Dashboard")

header_frame = tb.Frame(root, bootstyle="primary")
header_frame.pack(fill=X)

title_label = tb.Label(
    header_frame,
    text="FEED AUTOMATION CONTROL PANEL",
    font=("Segoe UI", 22, "bold"),
    bootstyle="inverse-primary"
)
title_label.pack(pady=10)

main_frame = tb.Frame(root, padding=15)
main_frame.pack(fill=BOTH, expand=True)

screen_width = root.winfo_screenwidth()
screen_height = root.winfo_screenheight()
root.geometry(f"{screen_width}x{screen_height}")

root.columnconfigure(0, weight=1)
root.rowconfigure(0, weight=1)
main_frame.columnconfigure(0, weight=1)

feed_data = []
try:
    with open('/home/sunfra/Desktop/feed_rawMaterial.csv', mode='r') as file:
        csv_reader = csv.reader(file)
        next(csv_reader)  
        feed_data = [row for row in csv_reader]
except FileNotFoundError:
    logging.error("Feed data file not found!")

font_label = ("Arial", 16)

def get_feed_types():

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        query = """
        SELECT shead_name
        FROM shead_config
        ORDER BY id
        """

        cursor.execute(query)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        feed_types = [row["shead_name"] for row in rows]
        return feed_types
    except Exception as e:
        print(f"Error fetching shead names: {e}")
        return []

def insert_running_log(shead_name):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        ton = 1
        client_id = 5
        date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        status = "running"

        query = """
        INSERT INTO batching_running_logs (shead_name, ton, client_id, date, status)
        VALUES (%s, %s, %s, %s, %s)
        """
        values = (shead_name, ton, client_id, date, status)
        cursor.execute(query, values)
        conn.commit()
        cursor.close()
        conn.close()
        print("Data inserted into running_logs table")
    except Exception as e:
        print(f"Error inserting running log: {e}")
        
def extract_five_digit_value(response):
    matches = re.search(r'\b\d{5}\b', response)
    return matches.group(0) if matches else None

def log_message(message):
    logging.info(message)
    if log_textbox.winfo_exists():
        log_textbox.config(state="normal")
        log_textbox.insert(tk.END, f"{message}\n")
        log_textbox.yview(tk.END)
        log_textbox.config(state="disabled")
        root.update()
        
def log_message2(message):
    print(message)

def fetch_and_process_feed():
    local_csv_file = "/home/sunfra/Desktop/feed_rawMaterial.csv"
    try:
        log_message2("Fetching feed formula from database...")
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        material_query = """
        SELECT material_name 
        FROM motor_config
        ORDER BY motor_number
        """
        cursor.execute(material_query)
        material_rows = cursor.fetchall()

        material_list = [row["material_name"] for row in material_rows]

        query = """
        SELECT feed_formulaType, feed_rawMaterial_name, quantity
        FROM feed_formula_detail
        WHERE type='Feed_Formula'
        """
        cursor.execute(query)
        rows = cursor.fetchall()

        if not rows:
            log_message2("No data found in database!")
            return

        formula_types = sorted(list({row["feed_formulaType"].lower() for row in rows}))
        headers = ["Material"] + formula_types

        materials = {}

        for material in material_list:
            materials[material] = {}

        for row in rows:
            material = row["feed_rawMaterial_name"]
            formula = row["feed_formulaType"].lower()
            qty = int(float(row["quantity"]))

            if material in materials:
                materials[material][formula] = qty

        cursor.close()
        conn.close()

        with open(local_csv_file, "w") as file:
            file.write(",".join(headers) + "\n")

            for material in material_list:  
                row = [material]
                for h in headers[1:]:
                    row.append(str(materials[material].get(h, 0)))
                file.write(",".join(row) + "\n")

        log_message2("CSV file successfully generated from database.")

        with open(local_csv_file, "r") as file:
            data = file.read().strip().split("\n")
            csv_data = [line.split(",") for line in data]

        log_message2("Processing feed data...")
        for row in csv_data:
            if row:
                log_message2(f"Processing row: {row}")

        log_message2("Feed data processing completed successfully.")

    except Exception as e:
        log_message2(f"Error fetching data from database: {e}")
                
def call_fetch_and_process_feed():
    log_message2("Calling fetch_and_process_feed...")
    fetch_and_process_feed()

def extract_and_display_value():
    if client2.connect():
        print("Connected to Modbus client.")
        try:
            result = client2.read_holding_registers(address=0, count=1, unit=2)
            if result.isError():
                print("Modbus Read Error:", result)
            else:
                indicator_value = result.registers[0]
                if indicator_value > 5000:
                    indicator_value = 0

                log_message(f"Extracted Value: {indicator_value}")
                extracted_value_label.config(text=f"Extracted Value: {indicator_value}")
        finally:
            client2.close()
    else:
        print("Failed to connect to Modbus client.")
    root.update()
    root.after(25, extract_and_display_value)


def new_table(index):
    tree.delete(*tree.get_children())
    for row_num, row in enumerate(feed_data):
        if index < len(row):
            tree.insert("", tk.END, values=(row[0], row[index]))

def append_to_csv(shead_no, timestamp, formula):
    csv_file = "/home/sunfra/Documents/script_log.csv"
    data = [timestamp, shead_no, formula]
    try:
        with open(csv_file, mode='a', newline='') as file:
            writer = csv.writer(file)
            if file.tell() == 0:
                writer.writerow(['Timestamp', 'Shead No', 'Formula'])
            writer.writerow(data)
        print(f"Data successfully written to {csv_file}")
    except Exception as e:
        print(f"Error: {e}")
       
def get_ist_timestamp():
    ist = pytz.timezone("Asia/Kolkata")
    return datetime.now(ist).strftime("%Y-%m-%d %H:%M:%S")

def process_feed(selected_feed):
    call_fetch_and_process_feed()
    if not selected_feed or selected_feed == "Choose a formula":
        log_message("Please select a valid Feed Type Formula!")
        return
    feed_types = get_feed_types()
    feed_mapping = {name: i + 1 for i, name in enumerate(feed_types)}

    index = feed_mapping.get(selected_feed)
    if not feed_data or index is None or index >= len(feed_data[0]):
        log_message("Invalid Feed Type Formula Selected!")
        return
    new_table(index)

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    formula = ""
    material_name = ""
    cumulative_weight = 0
    log_message(f"Processing Feed Type: {selected_feed}")
    current_material_label.config(text=f"Currently Running Material: {selected_feed}")
    root.update()

    log_message(f"Selected Formula: {selected_feed}")
    for row_num, row in enumerate(feed_data):
        if index < len(row):
            combined_value = f"{row[0]}-{row[index]}"
            formula += combined_value + " , "
            if row_num == 0:
                material_name = row[0]

    for row_num, row in enumerate(feed_data):
        time.sleep(2)
        if not client.connect():
            print("Failed to connect to the relay board.")
            return

        print("Turning CH ON...")
        COIL_ADDRESS = row_num
        response = client.write_coil(COIL_ADDRESS, True, unit=SLAVE_ID)

        if response.isError():
            print("Error writing coil ON:", response)
        else:
            print("Relay ON command successful")
        time.sleep(0.05)
        
        if index < len(row):
            try:
                current_weight = int(row[index])
                cumulative_weight += current_weight
                quantity = str(cumulative_weight).zfill(5)

                current_weight_label.config(text=f"Material Quantity: {current_weight}")
                cumulative_weight_label.config(text=f"Cumulative Expected Weight: {cumulative_weight}")

                root.update()
                material_name = row[0] if row and row[0].strip() else f"Row {row_num + 1}"
                current_material_label.config(text=f"Currently Running Material: {material_name}")
                log_message(f"\n[Row {row_num + 1}]")
                log_message(f"  Material: {material_name}")
                log_message(f"  Current Weight: {current_weight}")
                log_message(f"  Cumulative Expected Quantity: {quantity}")
                matched = False
                while not matched:
                    if client2.connect():
                        result = client2.read_holding_registers(address=0, count=1, unit=2)
                        if result.isError():
                            log_message("Modbus Read Error")
                        else:
                            indicator_value = result.registers[0]
                            if indicator_value > 5000:
                                indicator_value = 0
                            log_message(f"  Indicator Value: {indicator_value}")
                            extracted_value_label.config(text=f"Extracted Value: {indicator_value}")
                            if int(indicator_value) >= int(quantity):
                                log_message(f"  Match found for Cumulative Quantity: {quantity}")
                                matched = True
                        client2.close()
                    else:
                        log_message("Failed to connect to Modbus client.")
                client.write_coil(COIL_ADDRESS, False, unit=SLAVE_ID)
                print("Relay OFF after match.")
            except ValueError:
                log_message(f"Invalid data at row {row_num + 1}. Skipping.")
        else:
            log_message(f"Row {row_num + 1}: Index {index} out of range.")
    append_to_csv(selected_feed, timestamp, formula)
    insert_running_log(selected_feed)
    log_message("\nProcessing Completed Successfully!")
    current_material_label.config(text="Currently Running Material: None")
    root.update()

def stop_all():
    if client.connect():
        for pin_name, coil_address in pins.items():
            response = client.write_coil(coil_address, False, unit=SLAVE_ID)
            if response.isError():
                log_message(f"Failed to turn OFF relay {pin_name}")
            else:
                log_message(f"Relay {pin_name} turned OFF")
        client.close()
    else:
        log_message("Failed to connect to relay board to stop all relays.")


def on_feed_button_click(feed):
    process_feed(feed)

instruction_label = tk.Label(main_frame, text="Select a Feed Type Formula:", font=("Arial", 12))
instruction_label.grid(row=0, column=0, pady=10, sticky=tk.NS)

feed_types = get_feed_types()
feed_type_combobox = ttk.Combobox(main_frame, values=feed_types, state="readonly", font=("Arial", 8))
feed_button_frame = ttk.Frame(main_frame)
feed_button_frame.grid(row=2, column=0, pady=10, sticky=tk.NS)

for idx, feed in enumerate(feed_types):
    feed_button = tb.Button(feed_button_frame,text=feed,command=lambda feed=feed: on_feed_button_click(feed),bootstyle="success-outline", width=12)
    
    row = idx // 5  
    col = idx % 5  
    
    feed_button.grid(row=row, column=col, padx=5, pady=5)

stop_button = tb.Button(
    main_frame,
    text="⛔ STOP PROCESS",
    command=stop_all,
    bootstyle="danger",
    width=20
)
stop_button.grid(row=3, column=0, pady=10, sticky=tk.NS)

status_frame = tb.Labelframe(
    main_frame,
    text="Live Process Status",
    bootstyle="info",
    padding=15
)
status_frame.columnconfigure(0, weight=1)
status_frame.columnconfigure(1, weight=1)
status_frame.columnconfigure(2, weight=1)
status_frame.grid(row=4, column=0, pady=10)

current_material_label = tb.Label(
    status_frame,
    text="Currently Running Material: None",
    font=("Segoe UI", 14, "bold"),
    bootstyle="warning"
)
current_material_label.grid(column=0, row=0, padx=15, pady=5)

current_weight_label = tb.Label(
    status_frame,
    text="Material Quantity: 0",
    font=("Segoe UI", 14, "bold"),
    bootstyle="success"
)
current_weight_label.grid(column=1, row=0, padx=15, pady=5)

cumulative_weight_label = tb.Label(
    status_frame,
    text="Cumulative Expected Weight: 0",
    font=("Segoe UI", 14, "bold"),
    bootstyle="info"
)
cumulative_weight_label.grid(column=2, row=0, padx=15, pady=5)
extracted_value_frame = ttk.Frame(main_frame, padding=5)
extracted_value_frame.grid(row=5, column=0, pady=10)

extracted_value_label = tb.Label(
    extracted_value_frame,
    text="Extracted Value: N/A",
    font=("Segoe UI", 36, "bold"),
    bootstyle="danger"
)
extracted_value_label.grid(row=0, column=0, pady=10)

tree = ttk.Treeview(main_frame, columns=("Material", "Quantity"), show="headings")
tree.heading("Material", text="Material")
tree.heading("Quantity", text="Quantity")
tree.grid(row=6, column=0, pady=10)

log_label = tk.Label(main_frame, text="Process Logs:", font=("Arial", 12))
log_label.grid(row=7, column=0, pady=5)

log_textbox = tk.Text(
    main_frame,
    height=15,
    width=80,
    bg="#111111",
    fg="#00FF9C",
    insertbackground="white",
    font=("Consolas", 10),
    state="disabled"
)
log_textbox.grid(row=8, column=0, pady=5)

if ser:
    root.after(500, extract_and_display_value)

root.protocol("WM_DELETE_WINDOW", lambda: [stop_all(), root.destroy()])

root.mainloop()

