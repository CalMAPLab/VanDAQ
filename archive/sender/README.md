# Windows VOCUS / TofDaq bridge scripts

These scripts run on the **Windows PC** where TofDaq and the VOCUS PTR-MS software operate. They read mass-spectrum and engineering data from TofDaq shared memory and send pickled messages to the **Linux van** over ZeroMQ.

They are **not** the VanDAQ submitter ([submitter/vandaq_submitter.py](../../submitter/vandaq_submitter.py)), which ships `.sbm` files to a central server via SFTP.

## Active production path

| Machine | Software | Role |
|---------|----------|------|
| Windows (TofDaq host) | `VanDAQ_Sender_VOCUS_V1.py` | ZMQ PUSH pickled `{ms, eng}` to the van |
| Linux van | `vandaq_acquirer.py` + [acquirer/config/VOCUS.yaml](../../acquirer/config/VOCUS.yaml) | ZMQ PULL on port 6969 → POSIX queue → collector |

Start the Linux side from the repo root:

```bash
./vandaq_admin startup VOCUS
```

On Windows, edit `HOST` in `VanDAQ_Sender_VOCUS_V1.py` to the **van's IP address** (not `central.example.org`) and set the TofDaq Python API path in `sys.path.append(...)` for your install.

## Files

| File | Status |
|------|--------|
| `VanDAQ_Sender_VOCUS_V1.py` | **Use this** — mass spec + engineering SDOs via ZMQ |
| `VanDAQ_Sender_Vocus.py` | Early prototype — TCP only, mass spec only |
| `Vocus_Receiver.py` | Debug TCP listener — superseded by the Linux acquirer |

All contain example hostnames and hardcoded Windows paths. They are not part of CI.
