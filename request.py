# Copyright 2025 Klemen Bregar, Comsensus d.o.o.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import requests
from datetime import datetime, timedelta
import json


if '__main__' == __name__:

    now = datetime.now()
    now = now.replace(hour=0, minute=0, second=0, microsecond=0)
    print(now)
    date1 = (now - timedelta(days=44, hours=2)).strftime("%Y-%m-%dT%H:%M:%S")
    date2 = (now - timedelta(days=43, hours=2)).strftime("%Y-%m-%dT%H:%M:%S")

    print(date1, date2)

    headers = {
        'Content-Type': 'application/json'
        }

    data = {
        'start_datetime': date1,
        'end_datetime': date2,
        # 'optimization_strategy': 'no_optimization'
        # 'optimization_strategy': 'self-consumption'
        'optimization_strategy': 'collective_self-consumption'
    }

    url = 'http://127.0.0.1:8000/api/v1/simulation'

    response = requests.post(url, data=json.dumps(data))

    print(response.status_code)

    content = response.json()
    if isinstance(content, str):
        content = json.loads(content)

    print("before optimization")
    res = content['results']['before_optimization']
    print(f"self-consumption: {res['self_consumption']}")
    print(f"self-sufficiency: {res['self_sufficiency']}")
    print(f"cost: {res['expenses']}")
    print(f"CO2 emissions: {res['co2_emissions']}")
    print(f"imported energy: {res['imported_energy']}")
    print(f"exported energy: {res['exported_energy']}")
    
    print()
    print("after optimization")
    res = content['results']['after_optimization']
    print(f"self-consumption: {res['self_consumption']}")
    print(f"self-sufficiency: {res['self_sufficiency']}")
    print(f"cost: {res['expenses']}")
    print(f"CO2 emissions: {res['co2_emissions']}")
    print(f"imported energy: {res['imported_energy']}")
    print(f"exported energy: {res['exported_energy']}")
