"""

VanDAQ
Mobile Atmospheric Data Acquisition System

Author: Robert Jay (Robin) Weber
Affiliation: University of California, Berkeley

Copyright (c) 2025 The Regents of the University of California
Released under the BSD 3-Clause License.
"""

import queue
from threading import Lock, Thread
import dash
from dash import Dash 
from dash import dcc, html, Input, Output, ctx, State
import pandas as pd
import datetime
from  ipcqueue import posixmq
from threading import Thread, Lock
import time
import os

# Initialize the Dash app
app = dash.Dash(__name__)

engine = None
logger = None


instrument_queues = []

# Layout for the instrument control page
def layout_instrument_controls(configdict):
    global config
    global logger
    config = configdict
    logger = config.get('logger', None)
    controls = config.get("controls", [])
    control_elements = []

    for instrument in controls:
        instrument_name = instrument.get("instrument_name", "Unnamed Instrument")  
        elements = [html.H3(instrument_name, style={'margin-top': '20px'})]
        command_queue_config = instrument.get("queue_command", None)
        command_queue_name = command_queue_config.get("name") if command_queue_config else None
        response_queue_config = instrument.get("queue_response", None)
        response_queue_name = response_queue_config.get("name") if response_queue_config else None
        queues = {"instrument_name": instrument_name, "command_queue": command_queue_name, "response_queue": response_queue_name}
        widgets = instrument.get("widgets", [])
        for widget in widgets:
            # Button control
            button_name = widget.get("button")
            button_command = widget.get("command", "")
            if button_name and button_command:
                elements.append(
                    html.Button(
                        button_name,
                        id={"type": "button", "instrument": instrument_name, "name": button_name, "command_queue_name": command_queue_name, "command": button_command},
                        n_clicks=0,
                        style={'margin-right': '10px'}
                    )
                )

            # Checkbox control
            checkbox_name = widget.get("checkbox")
            if checkbox_name:
                command_checked = widget.get("command_checked", "")
                command_unchecked = widget.get("command_unchecked", "")
                commands = command_unchecked + '|' + command_checked
                if widget.get("checked", "") is True:
                    initial = [checkbox_name]
                else:
                    initial = []
                elements.append(
                    dcc.Checklist(
                        options=[checkbox_name],
                        value=initial,
                        id={"type": "checkbox", "instrument": instrument_name, "name": checkbox_name, "command_queue_name": command_queue_name, "commands": commands},
                        inline=True,
                        style={'margin-right': '10px'}
                    )
                )
            # Command input box
            if "command_box" in widget:
                label = widget["command_box"].get("label", "Command")
                command_terminator = widget["command_box"].get("command_terminator", "\r")
                elements.append(html.Div([
                    html.Label(label, style={'margin-right': '10px'}),
                    dcc.Input(
                        id={"type": "command-box", "instrument": instrument_name, "name": label, "command_queue_name": command_queue_name, 'command_terminator': command_terminator},
                        type="text",
                        placeholder=f"Enter command for {instrument_name}",
                        debounce=True,
                        style={'width': '100%', 'margin-right': '10px'}
                    ),
                ], style={'margin-top': '10px'}))
            # response display box
            if "response_box" in widget:
                line_height = widget.get("line-height", 2)

                response_box = dcc.Textarea(
                    id={"type": "response_box", "instrument": instrument_name, "name": "response_box"},
                    value="",
                    style={'width': '100%', 'height': f'{line_height}em', 'margin-top': '10px', 'background':'black', 'color':'white'}
                )
                elements.append(response_box)
                queues["response_box"] = response_box

        instrument_queues.append(queues)
        control_elements.append(html.Div(elements, style={'margin-bottom': '20px'}))
        control_elements.append(html.Hr(style={'margin-bottom': '20px', 'margin-top': '10px'}))
    return html.Div([
        dcc.Interval(id="poller", interval=500, n_intervals=0),
        html.H1('Instrument Controls', style={'text-align': 'left'}),
        html.Div(control_elements),
        html.Div(id="output_instrument_controls", style={"display": "none"})
    ])


# Callback for instrument controls
def instrument_controls(app, sqlengine, config): 
    global logger
    global replies
    global lock
    logger = config['logger']
    replies = []
    lock = Lock()
    Thread(target=check_queues, args=(engine, config, lock), daemon=True).start()

    # Pattern-matching callback
    @app.callback(
        Output("output_instrument_controls", "children"),
        [
            Input({"type": "button", "instrument": dash.ALL, "name": dash.ALL, "command_queue_name": dash.ALL, "command": dash.ALL}, "n_clicks"),
            Input({"type": "checkbox", "instrument": dash.ALL, "name": dash.ALL,  "command_queue_name": dash.ALL, "commands": dash.ALL}, "value"),
            Input({"type": "command-box", "instrument": dash.ALL, "name": dash.ALL,  "command_queue_name": dash.ALL, 'command_terminator': dash.ALL}, "value"),
        ],
    )
    def handle_controls(all_button_clicks, all_checkbox_values, all_command_box_values):
        # Figure out what triggered
        trig = ctx.triggered_id
        if trig is None:
            return "Nothing triggered yet"

        if trig["type"] == "button":
            # Send command to the appropriate queue
            command = trig.get("command")
            queue_name = trig.get("command_queue_name")
            if queue_name:
                # Find the corresponding command queue
                with lock:
                    queue = posixmq.Queue(queue_name)
                    if queue:
                        queue.put({"command":command})
                        logger.info(f"Sent command '{command}' to queue '{queue}'")
                    else:
                        logger.error(f"Failed to find queue '{queue_name}'")
            return f"Button clicked: {trig['instrument']} → {trig['name']}"

        elif trig["type"] == "checkbox":
            value = None
            for ids, val in zip(ctx.inputs_list[1], all_checkbox_values):
                if ids.get('id') == trig:
                    value = val   # this is the value for the triggered checkbox
                    break
            commands = trig.get("commands")
            if commands:
                commands = commands.split('|')
            queue_name = trig.get("command_queue_name")
            if commands and value == []:
                command = commands[0]
            else:
                command = commands[1]
            if queue_name:
                # Find the corresponding command queue
                with lock:
                    queue = posixmq.Queue(queue_name)
                    if queue:
                        queue.put({"command":command})
                        logger.info(f"Sent command '{command}' to queue '{queue}'")
                    else:
                        logger.error(f"Failed to find queue '{queue_name}'")
            return f"Checkbox changed: {trig['instrument']} → {trig['name']}"
        elif trig["type"] == "command-box":
            value = None
            for ids, val in zip(ctx.inputs_list[2], all_command_box_values):
                if ids.get('id') == trig:
                    value = val   # this is the value for the triggered checkbox
                    break
            command = value
            queue_name = trig.get("command_queue_name")
            if command and queue_name:
                # Find the corresponding command queue
                with lock:
                    mq_path = f"/dev/mqueue{queue_name}"
                    if os.path.exists(mq_path):
                        queue = posixmq.Queue(queue_name)
                    else:
                        logger.error(f"Queue file '{mq_path}' does not exist for command queue '{queue_name}'")
                        queue = None
                    if queue:
                        queue.put({"command":(command+trig["command_terminator"])})
                        logger.info(f"Sent command '{command}' to queue '{queue}'")
                    else:
                        logger.error(f"Failed to find queue '{queue_name}'")
            return f"Checkbox changed: {trig['instrument']} → {trig['name']}"
        else:
            return "Unknown trigger"


    @app.callback(
        Output({"type": "response_box", "instrument": dash.ALL, "name": "response_box"}, "value"),
        Input("poller", "n_intervals"),
        State({"type": "response_box", "instrument": dash.ALL, "name": "response_box"}, "value"),
        State({"type": "response_box", "instrument": dash.ALL, "name": "response_box"}, "id"),
        prevent_initial_call=True)
    def update_responseboxes(intervals,current_values, ids):
        # Drain the global queue into a dict instrument -> list of messages
        pending = {}
        new_values = []
        global replies
        global lock
        with lock:
            for r in replies:
                instr = r.get("instrument")
                response_text = r.get("response", "")
                if instr not in pending:
                    pending[instr] = []
                pending[instr].append(response_text)
            replies.clear()
        for current, id_dict in zip(current_values, ids):
            instr = id_dict["instrument"]
            extra = pending.get(instr, [])
            if extra:
                new_values.append((current or "") + "\n".join(extra))
            else:
                new_values.append(current)
        return new_values

def check_queues(engine, config, lock):
    global instrument_queues
    global replies
    while True:
        for qinfo in instrument_queues:
            response_queue_name = qinfo.get("response_queue")
            instrument_name = qinfo.get("instrument_name", "Unnamed Instrument")
            response_box = qinfo.get("response_box")
            # Check response queue
            with lock:
                if response_queue_name:
                    time.sleep(0.1)  # give time for the full message to arrive
                    try:
                        mq_path = f"/dev/mqueue{response_queue_name}"
                        if os.path.exists(mq_path):
                            response_queue = posixmq.Queue(response_queue_name)
                        else:
                            time.sleep(0.5)
                            continue
                    except Exception as e:
                        logger.debug(f"Failed to open response queue {response_queue_name}, check acquirer running? Error: {e}")
                        continue
                    try:
                        if response_queue.qsize() == 0:
                            continue
                        msg = response_queue.get()
                        if msg is not None and type(msg) is dict and "response" in msg:
                            msg['instrument'] = instrument_name
                            msg['response'] += '\n'
                            replies.append(msg)
                    except queue.Empty:
                        pass
        time.sleep(0.1)    

