import requests
from datetime import datetime
from dateutil import tz

# TODO handle request failure
# https://developers.home-assistant.io/docs/api/rest/
# returns [[duration of state in seconds, state, day of the week, sensor]]
def GetSensorJson(sensor: str, start_time='2025-03-01T00:00:00', end_time='2025-03-31T00:00:00'):
    # API Calls
    response = requests.get(
        f'http://homeassistant.mow/api/history/period/{start_time}?filter_entity_id={sensor}&minimal_response=true&end_time={end_time}',
        headers={
            'Authorization': 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiI4NDZkYTk4N2NhZWU0M2M1ODViNDRmZTZjZmY5N2ZlNiIsImlhdCI6MTc0MzMxMjQwOSwiZXhwIjoyMDU4NjcyNDA5fQ.EdZOSzBc0jEfNTHhpC6bo730XpCTpZlB_xruWH2mGiI'

        })

    # last_changed column appears to the be the timestamp in which the state changed to that value in the state column
    # so taking the last_change time of row N - last changed time of row N+1 should get you the duration of how long the
    # device was in the state set in row N
    obj = response.json()[0]  # the API can accepd multiple device entities but we only send one, grab the first one
    p_time = obj[1][
        'last_changed']  # skip the first entry since we don't get an accurate times due to the query lower bound
    p_state = obj[1]['state']
    out = []

    for i in range(2, len(obj)):
        c_time = obj[i]['last_changed']
        day_of_the_week = datetime.fromisoformat(p_time).astimezone(tz.gettz()).weekday()
        out.append([(datetime.fromisoformat(c_time) - datetime.fromisoformat(p_time)).total_seconds(), p_state, day_of_the_week, sensor])
        p_time = c_time
        p_state = obj[i]['state']
    return out

print(GetSensorJson('binary_sensor.doggie_park_presence_detector_occupancy'))