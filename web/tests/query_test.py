import datetime
from vandaq_measurements_query import get_measurements
from sqlalchemy import create_engine, and_
import statistics

# Database connection
engine = create_engine('postgresql://vandaq:p3st3r@localhost:5432/vandaq-dev', echo=False)

times = []

for i in range(0,1):
    start_time = datetime.datetime.now()

    df = get_measurements(engine, start_time=datetime.datetime.now()-datetime.timedelta(minutes=2))

    end_time = datetime.datetime.now()

    diff = end_time - start_time
    secs = diff.total_seconds()
    times.append(secs)

print("query average excution "+str(statistics.mean(times))+ 'secs')
