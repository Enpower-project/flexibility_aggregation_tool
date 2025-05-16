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

from fastapi import FastAPI
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
from ecmp_client import ECMPClient
from community.entity import Entity
import json
import numpy as np

app = FastAPI()

class SimulationParameters(BaseModel):
    start_datetime: str = Field(..., description="String in a datetime format (e.g., 2025-03-26T23:00:00)")
    end_datetime: str = Field(..., description="String in a datetime format (e.g., 2025-03-26T23:00:00)")
    optimization_strategy: str = Field(..., description="String with a name of optimization strategy (no_optimization, self-consumption, collective_self-consumption)")



def format_output_series(series):
    # generate result array
    time = (series.index.astype("int64") // 1_000_000).tolist()
    data = series.values.tolist()
    res = [[t, d] for t, d in zip(time, data)]

    return res

def generate_report_no(data):
    energy_cost = 0.00012
    grid_tarrif = 0.0001
    # calculate self-sufficiency for individual entities
    data_out = data.tail(96)
    production = data_out['pv_production_power']
    consumption_bss = data_out['consumption'] + data['bss_charge_power']
    consumption = data_out['consumption']
    self_consumption = production.combine(consumption_bss, func=np.minimum)
    grid_feed_in = data_out['grid_export_power']
    grid_import = data_out['grid_import_power']
    # convert power values into the Wh values (energy)
    # 15-min values
    consumption_wh = consumption * 0.25
    production_wh = production * 0.25
    self_consumption_wh = self_consumption * 0.25
    grid_feed_in_wh = grid_feed_in * 0.25
    grid_import_wh = grid_import * 0.25

    # sum the energies
    total_energy_demanded = consumption_wh.sum()
    total_energy_produced = production_wh.sum()
    total_grid_feed_in = grid_feed_in_wh.sum()
    total_grid_import = grid_import_wh.sum()
    self_consumed_energy = self_consumption_wh.sum()

    self_sufficiency_result = (self_consumed_energy / total_energy_demanded) * 100.0
    self_consumption_result = (self_consumed_energy / total_energy_produced) * 100.0

    cost = (grid_import_wh * energy_cost * 1.15 + grid_import_wh * grid_tarrif).sum()


    return {
        'total_demand': total_energy_demanded,
        'total_production': total_energy_produced,
        'total_export': total_grid_feed_in,
        'total_import': total_grid_import,
        'self_consumed_energy': self_consumed_energy,
        'self_sufficiency': self_sufficiency_result,
        'self_consumption': self_consumption_result,
        'consumption': consumption,
        'production': production,
        'stored_energy': data_out['bss_stored_energy'],
        'cost': cost
        }


def generate_report(data):
    energy_cost = 0.00012
    grid_tarrif = 0.0001
    # calculate self-sufficiency for individual entities
    data_out = data.tail(96)
    production = data_out['pv_production_power']
    consumption_bss = data_out['consumption'] + data['bss_charge_power']
    consumption = data_out['consumption']
    self_consumption = production.combine(consumption_bss, func=np.minimum)
    grid_feed_in = data_out['grid_export_power']
    grid_import = data_out['grid_import_power']
    local_import = data_out['local_import']
    # convert power values into the Wh values (energy)
    # 15-min values
    consumption_wh = consumption * 0.25
    production_wh = production * 0.25
    self_consumption_wh = self_consumption * 0.25
    grid_feed_in_wh = grid_feed_in * 0.25
    grid_import_wh = grid_import * 0.25
    local_import_wh = local_import * 0.25
    # sum the energies
    total_energy_demanded = consumption_wh.sum()
    total_energy_produced = production_wh.sum()
    total_grid_feed_in = grid_feed_in_wh.sum()
    total_grid_import = grid_import_wh.sum()
    self_consumed_energy = self_consumption_wh.sum()

    self_sufficiency_result = (self_consumed_energy / total_energy_demanded) * 100.0
    self_consumption_result = (self_consumed_energy / total_energy_produced) * 100.0

    cost = ((grid_import_wh * energy_cost * 1.15 + grid_import_wh * grid_tarrif) + (local_import_wh * energy_cost)).sum()

    return {
        'total_demand': total_energy_demanded,
        'total_production': total_energy_produced,
        'total_export': total_grid_feed_in,
        'total_import': total_grid_import,
        'self_consumed_energy': self_consumed_energy,
        'self_sufficiency': self_sufficiency_result,
        'self_consumption': self_consumption_result,
        'consumption': consumption,
        'production': production,
        'stored_energy': data_out['bss_stored_energy'],
        'cost': cost
        }


def surplus_allocation(data1, data2, data3):#, pricing):
    """This function provides allocation and allocation coefficients for the local surplus sharing to the energy community participants
    """
    allocation_coeff = [[], [], []]
    allocation = [[], [], []]

    for i in range(len(data1)):
        state = [data1.iloc[i], data2.iloc[i], data3.iloc[i]]

        for mp in range(len(state)):
            # calculate allocation coefficients for each metering point's injected surplus
            # customer c's local surplus
            # grid_export_power
            surplus = state[mp]['grid_export_power']
            # all customers' supplies/imports
            supplies = [state[customer]['grid_import_power'] for customer in range(len(state))]
            total_supply = sum(supplies) - supplies[mp]

            coeff = []
            alloc = []
            if 0.0 == surplus:
                coeff = [0.0 for item in state]
            else:
                for c in range(len(state)):
                    # calculate allocation coefficients per customer
                    if c == mp:
                        alcf = 0.0
                    elif 0.0 == total_supply:
                        alcf = 0.0
                    else:
                        alcf = supplies[c] / total_supply
                    coeff.append(alcf)
            alloc = [surplus*cf for cf in coeff]   

            allocation_coeff[mp].append(coeff)
            allocation[mp].append(alloc)

    return allocation_coeff, allocation
            

def aggregate_local_import(allocation):
    local_import = [[], [], []]

    for i in range(3):
        for j in range(len(allocation[i])):
            mp_sum = (allocation[0][j][i] + allocation[1][j][i] + allocation[2][j][i])#*0.25
            local_import[i].append(mp_sum)

    return local_import
              
                
                 

@app.post("/api/v1/simulation")
async def simulate(params: SimulationParameters):

    ecmp = ECMPClient(base_url="https://enpower.comsensus.eu/api/v1")
    users = ecmp.get_customers()
    customers = [id for id in users.keys()]
    customer_id = customers[0]
    print(f"Customer ID: {customer_id}")

    date1 = params.start_datetime
    date2 = params.end_datetime
    strategy = params.optimization_strategy

    # move start date for more realistic battery optimization
    date1 = (datetime.strptime(date1, "%Y-%m-%dT%H:%M:%S") - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%S")

    print(f"start: {date1}, end: {date2}")
    print(f"Optimization strategy: {strategy}")

    # now = datetime.now()
    # now = now.replace(hour=0, minute=0, second=0, microsecond=0)
    # print(now)
    
    # date1 = (now - timedelta(days=2, hours=2)).strftime("%Y-%m-%dT%H:%M:%S")
    # date2 = (now - timedelta(days=1, hours=2)).strftime("%Y-%m-%dT%H:%M:%S")

    entity1 = Entity(base_url="https://enpower.comsensus.eu/api/v1", customer_id=customer_id, metering_point_name='E003', pv_name='pv1', bss_name='BSS 139188', bss_capacity=55000.0, bss_max_power=8000.0, start_dt=date1, stop_dt=date2)
    entity2 = Entity(base_url="https://enpower.comsensus.eu/api/v1", customer_id=customer_id, metering_point_name='E004', pv_name='pv2', bss_name='BSS 136739', bss_capacity=55000.0, bss_max_power=8000.0, start_dt=date1, stop_dt=date2)
    entity3 = Entity(base_url="https://enpower.comsensus.eu/api/v1", customer_id=customer_id, metering_point_name='E007', pv_name='pv3', bss_name='BSS 137085', bss_capacity=110000.0, bss_max_power=16000.0, start_dt=date1, stop_dt=date2)

    # prepare empty/default output
    output = {
        'start_datetime': date1,
        'end_datetime': date2,
        'optimization_strategy': strategy,
        'results': {
            'self_consumption': 0.0,
            'self_sufficiency': 0.0,
            'co2_emissions': 0.0,
            'expenses': 0.0,
            'imported_energy': 0.0,
            'exported_energy': 0.0,
            'consumption': {},
            'production': {},
            'stored_energy': {}
        }
    }

    if 'no_optimization' == strategy:
        data1_no = entity1.get_entity_data().copy()
        data2_no = entity2.get_entity_data().copy()
        data3_no = entity3.get_entity_data().copy()
        data_combined_no = data1_no + data2_no + data3_no
        results_no = generate_report_no(data_combined_no)

        allocation_coefficients_no, allocation_no = surplus_allocation(data1_no, data2_no, data3_no)
        local_import_no = aggregate_local_import(allocation_no)

        data1_no['local_import'] = local_import_no[0]
        data2_no['local_import'] = local_import_no[1]
        data3_no['local_import'] = local_import_no[2]

        data1_no['grid_import_power'] = data1_no['grid_import_power'] - data1_no['local_import']
        data2_no['grid_import_power'] = data2_no['grid_import_power'] - data2_no['local_import']
        data3_no['grid_import_power'] = data3_no['grid_import_power'] - data3_no['local_import']

        data_combined = data1_no + data2_no + data3_no

        results = generate_report(data_combined)

        output = {
            'start_datetime': date1,
            'end_datetime': date2,
            'optimization_strategy': strategy,
            'results': {
                'before_optimization':{
                    'self_consumption': results_no['self_consumption'],
                    'self_sufficiency': results_no['self_sufficiency'],
                    'co2_emissions': 0.0,
                    'expenses': results_no['cost'],
                    'imported_energy': results_no['total_import'],
                    'exported_energy': results_no['total_export'],
                    'consumption': format_output_series(results_no['consumption']),
                    'production': format_output_series(results_no['production']),
                    'stored_energy': format_output_series(results_no['stored_energy'])
                },
                'after_optimization': {
                    'self_consumption': results['self_consumption'],
                    'self_sufficiency': results['self_sufficiency'],
                    'co2_emissions': 0.0,
                    'expenses': results['cost'],
                    'imported_energy': results['total_import'],
                    'exported_energy': results['total_export'],
                    'consumption': format_output_series(results['consumption']),
                    'production': format_output_series(results['production']),
                    'stored_energy': format_output_series(results['stored_energy'])
                }
            }
        }

  
    if 'self-consumption' == strategy:
        data1_no = entity1.get_entity_data().copy()
        data2_no = entity2.get_entity_data().copy()
        data3_no = entity3.get_entity_data().copy()

        allocation_coefficients_no, allocation_no = surplus_allocation(data1_no, data2_no, data3_no)
        local_import_no = aggregate_local_import(allocation_no)

        data1_no['local_import'] = local_import_no[0]
        data2_no['local_import'] = local_import_no[1]
        data3_no['local_import'] = local_import_no[2]

        data1_no['grid_import_power'] = data1_no['grid_import_power'] - data1_no['local_import']
        data2_no['grid_import_power'] = data2_no['grid_import_power'] - data2_no['local_import']
        data3_no['grid_import_power'] = data3_no['grid_import_power'] - data3_no['local_import']

        data_combined_no = data1_no + data2_no + data3_no

        results_no = generate_report(data_combined_no)

        data1 = entity1.self_consumption_optimization()
        data2 = entity2.self_consumption_optimization()
        data3 = entity3.self_consumption_optimization()

        allocation_coefficients, allocation = surplus_allocation(data1, data2, data3)
        local_import = aggregate_local_import(allocation)

        data1['local_import'] = local_import[0]
        data2['local_import'] = local_import[1]
        data3['local_import'] = local_import[2]

        data1['grid_import_power'] = data1['grid_import_power'] - data1['local_import']
        data2['grid_import_power'] = data2['grid_import_power'] - data2['local_import']
        data3['grid_import_power'] = data3['grid_import_power'] - data3['local_import']

        data_combined = data1 + data2 + data3
        results = generate_report(data_combined)

        output = {
            'start_datetime': date1,
            'end_datetime': date2,
            'optimization_strategy': strategy,
            'results': {
                'before_optimization':{
                    'self_consumption': results_no['self_consumption'],
                    'self_sufficiency': results_no['self_sufficiency'],
                    'co2_emissions': 0.0,
                    'expenses': results_no['cost'],
                    'imported_energy': results_no['total_import'],
                    'exported_energy': results_no['total_export'],
                    'consumption': format_output_series(results_no['consumption']),
                    'production': format_output_series(results_no['production']),
                    'stored_energy': format_output_series(results_no['stored_energy'])
                },
                'after_optimization': {
                    'self_consumption': results['self_consumption'],
                    'self_sufficiency': results['self_sufficiency'],
                    'co2_emissions': 0.0,
                    'expenses': results['cost'],
                    'imported_energy': results['total_import'],
                    'exported_energy': results['total_export'],
                    'consumption': format_output_series(results['consumption']),
                    'production': format_output_series(results['production']),
                    'stored_energy': format_output_series(results['stored_energy'])
                }
            }
        }

    elif 'collective_self-consumption' == strategy:
        data1_no = entity1.get_entity_data().copy()
        data2_no = entity2.get_entity_data().copy()
        data3_no = entity3.get_entity_data().copy()

        allocation_coefficients_no, allocation_no = surplus_allocation(data1_no, data2_no, data3_no)
        local_import_no = aggregate_local_import(allocation_no)

        data1_no['local_import'] = local_import_no[0]
        data2_no['local_import'] = local_import_no[1]
        data3_no['local_import'] = local_import_no[2]

        data1_no['grid_import_power'] = data1_no['grid_import_power'] - data1_no['local_import']
        data2_no['grid_import_power'] = data2_no['grid_import_power'] - data2_no['local_import']
        data3_no['grid_import_power'] = data3_no['grid_import_power'] - data3_no['local_import']

        data_combined_no = data1_no + data2_no + data3_no

        results_no = generate_report(data_combined_no)

        # get number of steps in data
        data_length = len(data1_no)

        # iterate over steps
        for i in range(data_length):
            entity1.set_state_from_data()
            entity2.set_state_from_data()
            entity3.set_state_from_data()

            # get entity state
            entity1_state = entity1.get_entity_state()
            entity2_state = entity2.get_entity_state()
            entity3_state = entity3.get_entity_state()

            # calculate charging power
            production = entity1_state.pv_production_power + entity2_state.pv_production_power + entity3_state.pv_production_power
            # prepare consumption data
            consumption1 = -entity1_state.consumption
            consumption2 = -entity2_state.consumption
            consumption3 = -entity3_state.consumption
            consumption = consumption1 + consumption2 +  consumption3

            # calculate bss_power to maximise self-consumption
            bss_power = -production - consumption

            # update entity1
            entity1._bss.set_power(bss_power, dt=900)
            entity1.update_state()
            entity1.step()
            # update entity2
            entity2._bss.set_power(bss_power, dt=900)
            entity2.update_state()
            entity2.step()
            # update entity3
            entity3._bss.set_power(bss_power, dt=900)
            entity3.update_state()
            entity3.step()

        data1 = entity1.get_entity_data().copy()
        data2 = entity2.get_entity_data().copy()
        data3 = entity3.get_entity_data().copy()

        allocation_coefficients, allocation = surplus_allocation(data1, data2, data3)
        local_import = aggregate_local_import(allocation)

        data1['local_import'] = local_import[0]
        data2['local_import'] = local_import[1]
        data3['local_import'] = local_import[2]

        data1['grid_import_power'] = data1['grid_import_power'] - data1['local_import']
        data2['grid_import_power'] = data2['grid_import_power'] - data2['local_import']
        data3['grid_import_power'] = data3['grid_import_power'] - data3['local_import']

        data_combined = data1 + data2 + data3
        results = generate_report(data_combined)

        output = {
            'start_datetime': date1,
            'end_datetime': date2,
            'optimization_strategy': strategy,
            'results': {
                'before_optimization':{
                    'self_consumption': results_no['self_consumption'],
                    'self_sufficiency': results_no['self_sufficiency'],
                    'co2_emissions': 0.0,
                    'expenses': results_no['cost'],
                    'imported_energy': results_no['total_import'],
                    'exported_energy': results_no['total_export'],
                    'consumption': format_output_series(results_no['consumption']),
                    'production': format_output_series(results_no['production']),
                    'stored_energy': format_output_series(results_no['stored_energy'])
                },
                'after_optimization': {
                    'self_consumption': results['self_consumption'],
                    'self_sufficiency': results['self_sufficiency'],
                    'co2_emissions': 0.0,
                    'expenses': results['cost'],
                    'imported_energy': results['total_import'],
                    'exported_energy': results['total_export'],
                    'consumption': format_output_series(results['consumption']),
                    'production': format_output_series(results['production']),
                    'stored_energy': format_output_series(results['stored_energy'])
                }
            }
        }
    else:
        pass
    
    json_str = json.dumps(output)


    return json_str



# uvicorn api:app --reload