---
platform: car1
instrument: LabJack_T7_1
type: LabJack
#verbose: 1
queue:
  name: "/dev-measurements"
  max_msg_size: 8000
  max_msgs: 50
connection_type: USB
device_type: T7
identifier: ANY
measurement_delay_secs: 0
data_freq_secs: 1

Parameters:
- SolarRadiation:
    signal_type: Analog
    channel_name: "AIN0"
    double_end: false
    preamp_gain: 201
    v_offset: 1.25
    v_per_unit: 0.00730
    aggregate: "mean"
    aggregate_hz: 10
    unit: "kW*m^-2"
    aquisition_type: "measurement_calibrated"
- SomeVoltage:
    signal_type: Analog
    channel_name: "AIN2"
    double_end: false
    preamp_gain: 1
    v_offset: 0
    v_per_unit: 1
    # aggregate: "mean"
    # aggregate_hz: 10
    unit: "volts"
    aquisition_type: "measurement_calibrated"

    # - DoorOpen:
#     signal_type: Digital
#     channel_name: "FIO0"
#     double_end: false
#     unit: "logical"
#     aquisition_type: "engineering"



logs:
  log_dir: "/home/vandaq/vandaq/acquirer/log"
  log_file: "acquirer_TSI_3789_CPC.log"
  log_level: "INFO"
  logger_name: "TSI_3789_CPC"
