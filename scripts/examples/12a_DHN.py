from model.reho import *
from pathlib import Path
from model.preprocessing.QBuildings import *
from model.postprocessing.postcompute_decentralized_districts import *
from model.preprocessing.QBuildings import QBuildingsReader
from model.preprocessing.data_generation import *

current_folder = Path(__file__).resolve().parent
folder = current_folder / 'results'

from model.reho import *
from pathlib import Path
from model.preprocessing.QBuildings import *
from model.postprocessing.postcompute_decentralized_districts import *
from model.preprocessing.QBuildings import QBuildingsReader
import pickle

current_folder = Path(__file__).resolve().parent
folder = current_folder / 'results'


def build_district(grids, scenario, transfo_id, nb_buildings):

    # connect to Suisse database
    reader = QBuildingsReader()
    reader.establish_connection('Suisse-old')
    qbuildings_data = reader.read_db(transfo_id, nb_buildings=nb_buildings)
    units = structure.initialize_units(scenario, grids=grids, district_units=True)

    # replace nan in buildings data
    for bui in qbuildings_data["buildings_data"]:
        qbuildings_data["buildings_data"][bui]["id_class"] = qbuildings_data["buildings_data"][bui]["id_class"].replace("nan", "II")

        if math.isnan(qbuildings_data["buildings_data"][bui]["U_h"]):
            qbuildings_data["buildings_data"][bui]["U_h"] = 0.00181

        if math.isnan(qbuildings_data["buildings_data"][bui]["HeatCapacity"]):
            qbuildings_data["buildings_data"][bui]["HeatCapacity"] = 120

        if math.isnan(qbuildings_data["buildings_data"][bui]["T_comfort_min_0"]):
            qbuildings_data["buildings_data"][bui]["T_comfort_min_0"] = 20

    return qbuildings_data, units


def execute_DW_with_increasing_BUI():

    transfo = 10889
    nb_buildings = 4

    # Define scenario
    Scenario = {'Objective': 'TOTEX', 'EMOO': {}, 'specific': [], "name": "multi_districts"}
    Scenario["exclude_units"] = ["ThermalSolar"]
    Scenario["enforce_units"] = ["HeatPump_DHN"]

    # you can specify if the DHN is based on CO2. If not, a water DHN is taken.
    Method = {"decomposed": False, "decentralized": True, "DHN_CO2": True}

    grids = structure.initialize_grids({'Electricity': {"Cost_demand_cst": 0.08, "Cost_supply_cst": 0.20},
                                        'NaturalGas': {"Cost_demand_cst": 0.06, "Cost_supply_cst": 0.20},
                                        "Heat": {"Cost_demand_cst": 0.001, "Cost_supply_cst": 0.005}})

    # select district data
    buildings_data, units = build_district(grids, Scenario, transfo, nb_buildings)

    # select weather data
    cluster = {'Location': 'Geneva', 'Attributes': ['I', 'T'], 'Periods': 10, 'PeriodDuration': 24}

    # specify the temperature of the DHN
    parameters = {"T_DHN_supply_cst": np.repeat(20.0, nb_buildings), "T_DHN_return_cst": np.repeat(15.0, nb_buildings)}

    # run opti
    reho_model = reho(buildings_data, units=units, grids=grids, cluster=cluster, method=Method, scenario=Scenario, parameters=parameters)

    reho_model.get_DHN_costs()  # run one optimization forcing DHN to find costs DHN connection per house

    reho_model.single_optimization()   # run optimization with DHN costs

    # get results
    reho_model.remove_all_ampl_lib()

    SR.save_results(reho_model, save=['xlsx', 'pickle'], filename='12a')
    return



if __name__ == '__main__':
    pd.set_option('display.max_rows', 500)
    pd.set_option('display.max_columns', 500)
    pd.set_option('display.width', 1000)
    execute_DW_with_increasing_BUI()

