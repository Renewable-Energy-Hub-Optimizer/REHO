import math
import re
from paths import *
from matplotlib import pyplot as plt
import pandas as pd
import numpy as np
import os
from PIL import Image
import plotly
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ---------------------------------------------------------------------------------------------
# Definition of colors and labels
cm = dict({'ardoise': '#413D3A', 'perle': '#CAC7C7', 'rouge': '#FF0000', 'groseille': '#B51F1F',
                    'canard': '#007480', 'leman': '#00A79F', 'salmon': '#FEA993', 'green': '#69B58A', 'yellow': '#FFB100', 'darkblue': '#1246B5', 'lightblue': '#8bacf4','perle_light': '#dad8d8',
                          'canard_light': '#4d9ea6', 'leman_light': '#4dc2bc', 'salmon_light': '#fec3b4',
                          'groseille_light': "#ff6666", 'darkyellow': '#A57300', 'dark': '#000000',
                          'yellow_light': '#FECC93'})

# Colors and labels for units and layers
layout = pd.read_csv(os.path.join(path_to_plotting, 'layout.csv'), index_col='Name').dropna(how='all')


# ---------------------------------------------------------------------------------------------

def dict_to_df(results, df):

    t = {(Scn_ID, Pareto_ID): results[Scn_ID][Pareto_ID][df]
         for Scn_ID in results.keys()
         for Pareto_ID in results[Scn_ID].keys()}

    df_merged = pd.concat(t.values(), keys=t.keys(), names=['Scn_ID', 'Pareto_ID'], axis=0)
    df_merged = df_merged.sort_index()

    return df_merged

def moving_average(data, n):
    return np.convolve(data, np.ones(n), 'valid') / n


def handle_zero_rows(df):
    is_zero_row = (df == 0).all(axis=1)

    return df.loc[~is_zero_row]


def prepare_dfs(df_eco, indexed_on='Scn_ID', neg=False):
    df_eco = df_eco.groupby(indexed_on).sum()
    indexes = df_eco.index.tolist()

    data_capex = df_eco.xs('investment', level='Category', axis=1).transpose()
    data_capex.index.names = ['Unit']
    data_capex = data_capex.reset_index().merge(layout, left_on="Unit", right_on='Name').set_index("Unit").fillna(0)

    data_opex = df_eco.xs('operation', level='Category', axis=1).transpose()
    indices = data_opex.index.get_level_values(0)
    new_indices = []
    [new_indices.append(tuple(idx.split("_", 1))) for idx in indices]
    for i, tup in enumerate(new_indices):
        if tup == ('costs', 'Electricity'):
            new_indices[i] = ('costs', 'Electrical_grid')
        elif tup == ('revenues', 'Electricity'):
            new_indices[i] = ('revenues', 'Electrical_grid_feed_in')
    data_opex.index = pd.MultiIndex.from_tuples(new_indices, names=['type', 'Layer'])

    data_opex.loc[('costs', 'PV'), :] = data_opex.loc[('avoided', 'PV')]
    if neg:
        indices = data_opex.index.get_level_values(0)
        neg_indices = indices.str.contains('avoided')
        neg_indices = neg_indices + indices.str.contains('revenues')
        data_opex.loc[neg_indices] = - data_opex.loc[neg_indices]
    data_opex = data_opex.reset_index().merge(layout, left_on='Layer', right_on='Name').set_index(['type', 'Layer'])

    return indexes, data_capex, data_opex


def remove_building_from_index(df):
    def filter_building_str(str):
        str_split = str.split("_")
        if len(str_split) > 2:
            new_idx = "_".join(str.split("_", 2)[:2])
        else:
            new_idx = str_split[0]
        return new_idx

    new_index = []
    index_frame = df.index.to_frame()
    if 'Unit' in index_frame.columns:
        for idx in index_frame['Unit']:
            new_index.append(filter_building_str(idx))
        index_frame['Unit'] = new_index
    if 'Hub' in index_frame.columns:
        for idx in index_frame['Hub']:
            new_index.append(filter_building_str(idx))
        index_frame['Hub'] = new_index

    index_modified = pd.MultiIndex.from_frame(index_frame)

    return df.set_index(index_modified)


def plot_performance(results, plot='costs', indexed_on='Scn_ID', label='FR_long', filename=None,
                     export_format='html', auto_open=False):
    """
        :param results: dictionary from REHO results pickle
        :param plot: choose among 'costs' and 'gwp'
        :param label: indicates the labels to use and so the language. Pick among 'FR_long', 'FR_short',
         'EN_long', 'EN_short'
        :param indexed_on: whether the results should be grouped on Scn_ID or Pareto_ID
        :param filename: name of the plot
        :param export_format: can be either html, png or plotly_plot
        :param auto_open: if export_format is html, to open it automatically in your browser
        param scaling_factor: scaling factor for the plot if a linear assumption is made
        :return:
    """

    df_eco = dict_to_df(results, 'df_economics')

    change_data = pd.DataFrame()
    change_data.index = ['col_1', 'col_2', 'x_axis_1', 'x_axis_2', 'y_axis', 'keyword', 'total', 'unites']
    lang = re.split('_', label)[0]
    if plot == 'costs':
        change_data['FR'] = ['Costs_Unit_inv', 'price', 'CAPEX', 'OPEX', 'Coûts [CHF/an]', 'Coûts', 'TOTEX', 'CHF']
        change_data['EN'] = ['Costs_Unit_inv', 'price', 'CAPEX', 'OPEX', 'Costs [CHF/y]', 'Costs', 'TOTEX', 'CHF']
        df_eco = df_eco.xs('costs', level='Perf_type')
    elif plot == 'gwp':
        change_data['FR'] = ['GWP_Unit_constr', 'gwp', 'Construction', 'Réseau', 'GWP [kgCO2/an]', 'Émissions', 'Total',
                             'kgCO2']
        change_data['EN'] = ['GWP_Unit_constr', 'gwp', 'Construction', 'Grid', 'GWP [kgCO2/y]', 'Emissions', 'Total',
                             'kgCO2']
        df_eco = df_eco.xs('impact', level='Perf_type')

    indexes, data_capex, data_opex = prepare_dfs(df_eco, indexed_on, True)

    x1 = list(range(len(indexes)))
    x2 = [x + 1 / 3 for x in x1]
    xtick = [x + 1 / 6 for x in x1]
    capex = data_capex[indexes].sum(axis=0).astype(int).reset_index(drop=True)
    capex_text = ["<b>" + change_data.loc['x_axis_1', lang] + "</b><br>" + str(cp) + change_data.loc['unites', lang]
                  for cp in capex]
    opex = data_opex[indexes].sum(axis=0).astype(int).reset_index(drop=True)
    pos_opex = data_opex[indexes][data_opex[indexes] > 0].sum(axis=0).astype(int).reset_index(drop=True)
    opex_text = ["<b>" + change_data.loc['x_axis_2', lang] + "</b><br>" + str(op) + change_data.loc['unites', lang]
                 for op in opex]

    fig = go.Figure()
    neg_opex = opex - pos_opex
    text_placeholder = 0.04 * max(max(capex - neg_opex), max(capex + pos_opex), max(pos_opex - neg_opex))

    for i in range(len(indexes)):
        fig.add_annotation(x=x2[i], y=-text_placeholder,
                           text=opex_text[i], font=dict(size=10),
                           textangle=0, align='center', valign='top',
                           showarrow=False)
        fig.add_annotation(x=x1[i], y=-text_placeholder,
                           text=capex_text[i], font=dict(size=9),
                           textangle=0, align='center', valign='top',
                           showarrow=False
                           )
        fig.add_annotation(x=xtick[i], y=max(capex[i], pos_opex[i], capex[i] + opex[i]) + max(capex + opex) * 0.04,
                           text="<b>" + change_data.loc['total', lang] + "</b><br>" + str(capex[i] + opex[i]) +
                                change_data.loc['unites', lang],
                           font=dict(size=9, color=cm['darkblue']),
                           textangle=0, align='center', valign='top',
                           showarrow=False
                           )
    for line, tech in data_capex.iterrows():
        if tech.loc[indexes].sum() > 0:
            fig.add_trace(
                go.Bar(name=tech[label], x=x1,
                       y=tech[indexes], width=1 / 3,
                       marker_color=tech["ColorPastel"],
                       hovertemplate='<b>' + tech[label] + '</b>' +
                                     '<br>' + change_data.loc['keyword', lang] + ': %{y:.0f}' +
                                     change_data.loc['unites', lang],
                       # text=unit_to_plot[label],
                       legendgroup='group1',
                       legendgrouptitle_text=change_data.loc['x_axis_1', lang],
                       showlegend=True))
    for line, layer in data_opex.iterrows():
        if abs(layer.loc[indexes].sum()) > 0:
            fig.add_trace(
                go.Bar(name=layer[label],
                       x=x2,
                       y=layer[indexes],
                       marker=dict(color=layer["ColorPastel"]),
                       legendgroup='group2',
                       legendgrouptitle_text=change_data.loc['x_axis_2', lang],
                       # text=data_opex[label],
                       showlegend=True,
                       width=1 / 3,
                       hovertemplate='<b>' + layer[label] + '</b>' +
                                     '<br>' + change_data.loc['keyword', lang] + ': %{y:.0f}' + change_data.loc[
                                         'unites', lang])
            )
    fig.add_trace(
        go.Bar(
            name=change_data.loc['total', lang],
            x=xtick, y=capex + opex,
            width=1 / 6, showlegend=False,
            hovertemplate="<b>" + change_data.loc['total', lang] + "</b><br>%{y:.0f}" + change_data.loc['unites', lang],
            marker=dict(color=cm['lightblue'], opacity=1)
        )
    )
    fig.update_layout(barmode="relative",
                      bargap=0,
                      template='plotly_white',
                      margin=dict(l=50, r=50, t=50, b=50),
                      xaxis=dict(
                          tickmode='array',
                          tickvals=xtick,
                          ticktext=indexes),
                      yaxis=dict(title=change_data.loc['y_axis', lang])
                      )
    if filename is not None:
        if not os.path.isdir(os.path.dirname(filename)):
            os.makedirs(os.path.dirname(filename))
        if 'html' == export_format:
            fig.write_html(filename + '.' + export_format)
        if 'png' == export_format:
            fig.write_image(filename + '.' + export_format)
    if auto_open:
        fig.show()
    return fig

def plot_actors(results, plot='costs', indexed_on='Scn_ID', label='FR_long', filename=None,
                            export_format='html', auto_open=False):
    """
        :param results: dictionary from REHO results pickle
        :param plot: choose among 'costs' and 'gwp'
        :param label: indicates the labels to use and so the language. Pick among 'FR_long', 'FR_short',
         'EN_long', 'EN_short'
        :param indexed_on: whether the results should be grouped on Scn_ID or Pareto_ID
        :param filename: name of the plot
        :param export_format: can be either html, png or plotly_plot
        :param auto_open: if export_format is html, to open it automatically in your browser
        param scaling_factor: scaling factor for the plot if a linear assumption is made
        :return:
    """

    df_eco = dict_to_df(results, 'df_economics')

    change_data = pd.DataFrame()
    change_data.index = ['col_1', 'col_2', 'x_axis_1', 'x_axis_2', 'y_axis', 'keyword', 'total', 'unites', 'leg_1',
                         'leg_2']
    lang = re.split('_', label)[0]
    if plot == 'costs':
        change_data['FR'] = ['Costs_Unit_inv', 'price', 'Coûts', 'Revenus', '[CHF/an]', 'Coûts', 'TOTEX', 'CHF', 'OPEX',
                             'CAPEX']
        change_data['EN'] = ['Costs_Unit_inv', 'price', 'Costs', 'Income', '[CHF/y]', 'Costs', 'TOTEX', 'CHF', 'OPEX',
                             'CAPEX']
        df_eco = df_eco.xs('costs', level='Perf_type')
    elif plot == 'gwp':
        change_data['FR'] = ['GWP_Unit_constr', 'gwp', 'Emissions', 'Evitées', 'GWP [kgCO2/an]', 'Émissions', 'Total',
                             'kgCO2', 'Réseau', 'Constr']
        change_data['EN'] = ['GWP_Unit_constr', 'gwp', 'Emissions', 'Avoided', 'GWP [kgCO2/y]', 'Emissions', 'Total',
                             'kgCO2', 'Grid', 'Constr']
        df_eco = df_eco.xs('impact', level='Perf_type')

    indexes, data_capex, data_opex = prepare_dfs(df_eco, indexed_on, False)

    costs = pd.concat([data_capex, data_opex.xs('costs', level='type')],
                      keys=['investment', 'operation'], names=['Category'])
    revenues = data_opex.loc[['avoided', 'revenues'], :]
    costs = costs[costs[indexes].sum(axis=1) > 0]
    revenues = revenues[revenues[indexes].sum(axis=1) > 0]
    totex = costs[indexes].sum(axis=0) - revenues[indexes].sum(axis=0)
    revenues = revenues.reindex(columns=costs.columns.tolist())

    x1 = list(range(len(indexes)))
    x2 = [x + 1 / 3 for x in x1]
    xtick = [x + 1 / 6 for x in x1]
    revenues_sum = revenues[indexes].sum(axis=0).astype(int).reset_index(drop=True)
    costs_sum = costs[indexes].sum(axis=0).astype(int).reset_index(drop=True)
    revenues_text = ["<b>" + change_data.loc['x_axis_2', lang] + "</b><br>" + str(cp) + change_data.loc['unites', lang]
                     for cp in revenues_sum]
    costs_text = ["<b>" + change_data.loc['x_axis_1', lang] + "</b><br>" + str(op) + change_data.loc['unites', lang]
                  for op in costs_sum]
    totex_text = ["<b>" + change_data.loc['total', lang] + "</b><br>" + str(tot) + change_data.loc['unites', lang]
                  for tot in totex.astype(int)]

    fig = go.Figure()
    for i in range(len(indexes)):
        fig.add_annotation(x=x2[i], y=-0.04 * max(max(revenues_sum), max(costs_sum)),
                           text=revenues_text[i], font=dict(size=10),
                           textangle=0, align='center', valign='top',
                           showarrow=False)
        fig.add_annotation(x=x1[i], y=-0.04 * max(max(revenues_sum), max(costs_sum)),
                           text=costs_text[i], font=dict(size=9),
                           textangle=0, align='center', valign='top',
                           showarrow=False
                           )
        fig.add_annotation(x=xtick[i], y=costs_sum[i] + 0.04 * max(max(revenues_sum), max(costs_sum)),
                           text=totex_text[i],
                           font=dict(size=9, color=cm['darkblue']),
                           textangle=0, align='center', valign='top',
                           showarrow=False
                           )
        # fig.add_annotation(
        #     x=x1[i], y=costs_sum[i] * 0.99, ax=x1[i], ay=costs_sum[i] - 0.04 * max(costs_sum),
        #     axref='x', ayref='y', text='',
        #     showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=1, arrowcolor='black'
        # )
        # if revenues_sum[i] > 0:
        #     fig.add_annotation(
        #         x=x2[i], ay=totex[i] + 0.04 * max(totex),
        #         ax=x2[i], y=totex[i] * 1.01,
        #         axref='x', ayref='y', text='',
        #         showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=1, arrowcolor='black'
        #     )

    fig.add_trace(
        go.Bar(name=change_data.loc['total', lang], x=x2,
               y=totex,
               legendgroup='group3',
               legendgrouptitle_text=change_data.loc['total', lang],
               marker=dict(color=cm['darkblue'], opacity=0),
               showlegend=False,
               # texttemplate=totex_text,
               hovertemplate=None,
               # textposition='inside',
               # textfont=dict(size=9, color=cm['darkblue']),
               width=1 / 6
               )
    )
    for line, tech in costs.xs('investment', level='Category').iterrows():
        if tech.loc[indexes].sum() > 0:
            fig.add_trace(
                go.Bar(name=tech[label], x=x1,
                       y=tech[indexes], width=1 / 3,
                       marker_color=tech["ColorPastel"],
                       hovertemplate='<b>' + tech[label] + '</b>' +
                                     '<br>' + change_data.loc['keyword', lang] + ': %{y:.0f}' +
                                     change_data.loc['unites', lang],
                       legendgroup='group1',
                       legendgrouptitle_text=change_data.loc['leg_2', lang],
                       showlegend=True))
    for line, tech in costs.xs('operation', level='Category').iterrows():
        if line == costs.xs('operation', level='Category').index[-1]:
            fig.add_trace(
                go.Bar(name=tech[label], x=x1,
                       y=tech[indexes], width=1 / 3,
                       marker_color=tech["ColorPastel"],
                       hovertemplate='<b>' + tech[label] + '</b>' +
                                     '<br>' + change_data.loc['keyword', lang] + ': %{y:.0f}' +
                                     change_data.loc['unites', lang],
                       legendgroup='group2',
                       legendgrouptitle_text=change_data.loc['leg_1', lang],
                       text='&#8593;', textposition='auto',
                       showlegend=True))
        else:
            fig.add_trace(
                go.Bar(name=tech[label], x=x1,
                       y=tech[indexes], width=1 / 3,
                       marker_color=tech["ColorPastel"],
                       hovertemplate='<b>' + tech[label] + '</b>' +
                                     '<br>' + change_data.loc['keyword', lang] + ': %{y:.0f}' +
                                     change_data.loc['unites', lang],
                       legendgroup='group2',
                       legendgrouptitle_text=change_data.loc['leg_1', lang],
                       showlegend=True))
    for line, layer in revenues.iterrows():
        if revenues.index[0] == line:
            fig.add_trace(
                go.Bar(name=layer[label],
                       x=x2,
                       y=layer[indexes],
                       marker=dict(color=layer["ColorPastel"]),
                       legendgroup='group2',
                       legendgrouptitle_text=change_data.loc['x_axis_2', lang],
                       showlegend=True,
                       text='&#8595;', textposition='auto',
                       width=1 / 3,
                       hovertemplate='<b>' + layer[label] + '</b>' +
                                     '<br>' + change_data.loc['keyword', lang] + ': %{y:.0f}' + change_data.loc[
                                         'unites', lang])
            )
        else:
            fig.add_trace(
                go.Bar(name=layer[label],
                       x=x2,
                       y=layer[indexes],
                       marker=dict(color=layer["ColorPastel"]),
                       legendgroup='group2',
                       legendgrouptitle_text=change_data.loc['x_axis_2', lang],
                       showlegend=True,
                       width=1 / 3,
                       hovertemplate='<b>' + layer[label] + '</b>' +
                                     '<br>' + change_data.loc['keyword', lang] + ': %{y:.0f}' + change_data.loc[
                                         'unites', lang])
            )
    # fig.add_trace(
    #     go.Bar(
    #         name=change_data.loc['total', lang],
    #         x=xtick, y=totex,
    #         width=1 / 6, showlegend=False,
    #         hovertemplate=totex_text,
    #         marker=dict(color=cm['darkblue'], opacity=0.7)
    #     )
    # )

    fig.update_layout(barmode="relative",
                      bargap=0,
                      template='plotly_white',
                      margin=dict(l=50, r=50, t=50, b=50),
                      xaxis=dict(
                          tickmode='array',
                          tickvals=xtick,
                          ticktext=indexes),
                      yaxis=dict(title=change_data.loc['y_axis', lang])
                      )
    if filename is not None:
        if not os.path.isdir(os.path.dirname(filename)):
            os.makedirs(os.path.dirname(filename))
        if 'html' == export_format:
            fig.write_html(filename + '.' + export_format)
        if 'png' == export_format:
            fig.write_image(filename + '.' + export_format)
    if auto_open:
        fig.show()
    return fig

def plot_pareto(results, label='FR_long', color='ColorPastel', auto_open=False):

    df_performance = dict_to_df(results, 'df_Performance').loc[
        (slice(None), slice(None), 'Network'),
        ["Costs_op", "Costs_inv", "Costs_grid_connection", "Costs_rep", "GWP_op", "GWP_constr"]].reset_index(['Scn_ID', 'Hub'])
    era = dict_to_df(results, 'df_Buildings').loc[(slice(None), 1, slice(None))].ERA.sum()
    df_performance["CAPEX"] = df_performance["Costs_inv"] + df_performance["Costs_rep"]
    df_performance["OPEX"] = df_performance["Costs_op"] + df_performance["Costs_grid_connection"]
    df_performance["TOTEX"] = df_performance["CAPEX"] + df_performance["OPEX"]
    df_performance["GWP"] = df_performance["GWP_op"] + df_performance["GWP_constr"]

    fig = make_subplots(specs=[[{"secondary_y": True}]])


    fig.add_trace(go.Scatter(
        x=list(df_performance.index),
        y=df_performance["CAPEX"].round(2),
        marker=dict(color=layout.loc["CAPEX", color]),
        line=dict(dash='dash'),
        mode="lines+markers",
        name="CAPEX",
    ))

    fig.add_trace(go.Scatter(
        x=list(df_performance.index),
        y=df_performance["OPEX"].round(2),
        marker=dict(color=layout.loc["OPEX", color]),
        line=dict(dash='dash'),
        mode="lines+markers",
        name="OPEX",
    ))

    fig.add_trace(go.Scatter(
        x=list(df_performance.index),
        y=df_performance["TOTEX"].round(2),
        marker=dict(color=layout.loc["TOTEX", color]),
        mode="lines+markers",
        name="TOTEX",
    ))

    fig.add_trace(go.Scatter(
        x=list(df_performance.index),
        y=df_performance["GWP"].round(2),
        marker=dict(size=10, color=layout.loc["GWP", color], symbol='diamond'),
        mode="markers+text",
        name="GWP",
        text=df_performance["GWP"].round(2),
        textposition="top right",
        yaxis="y2",
    ))

    fig.update_layout(
        template='plotly_white',
        xaxis=dict(
            title="Scenario",
        ),
        yaxis=dict(
            title="Costs [CHF/yr]",
            titlefont=dict(
                color=layout.loc["TOTEX", color]
            ),
            tickfont=dict(
                color=layout.loc["TOTEX", color]
            )
        ),
        yaxis2=dict(
            title="GWP [kgkgCO2/yr]",
            titlefont=dict(
                color=layout.loc["GWP", color]
            ),
            tickfont=dict(
                color=layout.loc["GWP", color]
            )
        )
    )

    if auto_open:
        fig.show()
    return fig

def plot_pareto_old(results, name_list=None, objectives=["CAPEX", "OPEX"], style='plotly', annotation="TOTEX",
                annot_offset=0, legend=True, save_fig=False, name_fig='pareto', format_fig='png'):

    df_performance_dict = {}
    # for results in results_list:
    df_performance = dict_to_df(results, 'df_Performance').loc[
        (slice(None), slice(None), 'Network'), ["Costs_op", "Costs_inv", "Costs_grid_connection", "Costs_rep",
                                                "GWP_op", "GWP_constr"]].reset_index(['Scn_ID', 'Hub'])
    era = dict_to_df(results, 'df_Buildings').loc[(slice(None), 1, slice(None))].ERA.sum()
    df_performance["CAPEX"] = df_performance["Costs_inv"] + df_performance["Costs_rep"]
    df_performance["OPEX"] = df_performance["Costs_op"] + df_performance["Costs_grid_connection"]
    df_performance["TOTEX"] = df_performance["CAPEX"] + df_performance["OPEX"]
    df_performance["GWP"] = df_performance["GWP_op"] + df_performance["GWP_constr"]
    df_performance_dict[df_performance.loc[1, "Scn_ID"]] = df_performance[
                                                                ["CAPEX", "OPEX", "TOTEX", "GWP"]].sort_values(
        by=objectives[0]) / era

    if name_list is None:
        name_list = list(df_performance_dict.keys())

    if objectives[0] == "CAPEX":
        obj_x = "CAPEX [CHF/m$^2$yr]"
    elif objectives[0] == "TOTEX":
        obj_x = "TOTEX [CHF/m$^2$yr]"
    if objectives[1] == "OPEX":
        obj_y = "OPEX [CHF/m$^2$yr]"
    elif objectives[1] == "GWP":
        obj_y = "GWP [kgkgCO2/m$^2$yr]"

    if style == 'matplotlib':

        fig, ax = plt.subplots()

        for i, scenario in enumerate(list(df_performance_dict.keys())):
            ax.plot(df_performance_dict[scenario][objectives[0]], df_performance_dict[scenario][objectives[1]],
                    marker='.', linestyle='--', color=cm[list(cm.keys())[i + 3]])
            for sc_i in df_performance_dict[scenario].index:
                if annotation is not None:
                    value = format((df_performance_dict[scenario].loc[sc_i, annotation]), '.2f')
                    ax.annotate(str(sc_i) + ": " + str(value),
                                xy=(df_performance_dict[scenario].loc[sc_i, objectives[0]] + annot_offset,
                                    df_performance_dict[scenario].loc[sc_i, objectives[1]] + annot_offset),
                                color=cm[list(cm.keys())[i + 3]],
                                size=10)

        plt.title(objectives[0] + "-" + objectives[1] + " Pareto")
        plt.xlabel(obj_x)
        plt.ylabel(obj_y)

        if legend:
            plt.legend(labels=name_list, loc='upper right', fancybox=True, shadow=True)

        if save_fig:
            plt.tight_layout()
            plt.savefig((name_fig + '.' + format_fig), format=format_fig, dpi=300)

        plt.show()

    else:

        fig = go.Figure()

        for scenario in df_performance_dict.keys():
            fig.add_trace(go.Scatter(
                x=df_performance_dict[scenario][objectives[0]].round(2),
                y=df_performance_dict[scenario][objectives[1]].round(2),
                mode="lines+markers+text",
                name=scenario,
                text=df_performance_dict[scenario][annotation].round(2),
                textposition="top right"
            ))

        if objectives[0] == "CAPEX":
            obj_x = "CAPEX [CHF/m2/yr]"
        elif objectives[0] == "TOTEX":
            obj_x = "TOTEX [CHF/m2/yr]"

        if objectives[1] == "OPEX":
            obj_y = "OPEX [CHF/m2/yr]"
        elif objectives[1] == "GWP":
            obj_y = "GWP [kgkgCO2/m2/yr]"

        fig.update_layout(
            title_text=objectives[0] + "-" + objectives[1] + " Pareto",
            xaxis_title=obj_x,
            yaxis_title=obj_y,
            font=dict(
                size=16,
            )
        )

        return fig


def plot_pareto_units(results, objectives=["CAPEX", "OPEX"], label='FR_long', color='ColorPastel',
                      save_fig=False, name_fig='pareto_units', format_fig='png'):

    scenario = list(results.keys())[0]
    ids = list(results[scenario].keys())
    era = results[scenario][ids[0]]['df_Buildings'].ERA.sum()

    df_unit = dict_to_df(results, 'df_Unit')
    df_performance = dict_to_df(results, 'df_Performance')

    df_performance = df_performance.xs((scenario, 'Network'), level=('Scn_ID', 'Hub'))
    df_performance["CAPEX"] = df_performance["Costs_inv"] + df_performance["Costs_rep"]
    df_performance["OPEX"] = df_performance["Costs_op"] + df_performance["Costs_grid_connection"]
    df_performance["TOTEX"] = df_performance["CAPEX"] + df_performance["OPEX"]
    df_performance["GWP"] = df_performance["GWP_op"] + df_performance["GWP_constr"]
    df_performance = df_performance.sort_values(by=objectives[0])

    if objectives[0] == "CAPEX":
        units_stack = "Costs_Unit_inv"
    elif objectives[0] == "TOTEX":
        units_stack = "GWP_Unit_constr"

    if objectives[1] == "OPEX":
        grid_stack = "Costs_op"
    if objectives[1] == "GWP":
        grid_stack = "GWP_op"


    PV = df_unit[df_unit.index.get_level_values('Unit').str.contains('PV')]
    PV = PV.groupby(level='Pareto_ID', sort=False).sum() / era

    EH = df_unit[df_unit.index.get_level_values('Unit').str.contains('ElectricalHeater')]
    EH = EH.groupby(level='Pareto_ID', sort=False).sum() / era

    BAT = df_unit[df_unit.index.get_level_values('Unit').str.contains('Battery')]
    BAT = BAT.groupby(level='Pareto_ID', sort=False).sum() / era

    BO = df_unit[df_unit.index.get_level_values('Unit').str.contains('NG_Boiler')]
    BO = BO.groupby(level='Pareto_ID', sort=False).sum() / era

    HP = df_unit[df_unit.index.get_level_values('Unit').str.contains('HeatPump_Air')]
    HP = HP.groupby(level='Pareto_ID', sort=False).sum() / era

    HS = df_unit[df_unit.index.get_level_values('Unit').str.contains('Tank')]
    HS = HS.groupby(level='Pareto_ID', sort=False).sum() / era

    idx = np.arange(0, 1, 1 / (len(PV.index)))
    width = 0.4 * 1 / (len(PV.index))

    # Plotting
    fig, ax = plt.subplots()
    fig.set_size_inches(10, 5)

    ax.bar((idx - 0.5 * width), BO[units_stack], label=layout.loc['Boiler', label], width=width,
        color=layout.loc['Boiler', color],
        edgecolor='black')
    ax.bar((idx - 0.5 * width), HP[units_stack], bottom=BO[units_stack], label=layout.loc['HeatPump_Air', label],
        width=width,
        color=layout.loc['HeatPump_Air', color],
        edgecolor='black')
    ax.bar((idx - 0.5 * width), EH[units_stack], bottom=HP[units_stack] + BO[units_stack],
        label=layout.loc['ElectricalHeater', label], width=width, color=layout.loc['ElectricalHeater', color],
        edgecolor='black')
    ax.bar((idx - 0.5 * width), PV[units_stack],
        bottom=EH[units_stack] + HP[units_stack] + BO[units_stack],
        label=layout.loc['PV', label], width=width, color=layout.loc['PV', color],
        edgecolor='black')
    ax.bar((idx - 0.5 * width), HS[units_stack],
        bottom=PV[units_stack] + EH[units_stack] + HP[units_stack] + BO[units_stack],
        label=layout.loc['WaterTankSH', label], width=width, color=layout.loc['WaterTankSH', color],
        edgecolor='black')
    ax.bar((idx - 0.5 * width), BAT[units_stack],
        bottom=HS[units_stack] + PV[units_stack] + EH[units_stack] + HP[units_stack] + BO[units_stack],
        label=layout.loc['Battery', label], width=width, color=layout.loc['Battery', color],
        edgecolor='black')
    ax.bar((idx + 0.5 * width), df_performance[grid_stack] / era, label="Resources", width=width,
        color=cm['salmon'],
        edgecolor='black')
    if objectives[1] == "OPEX":
        ax.bar((idx + 0.5 * width), df_performance.Costs_grid_connection / era,
            bottom=df_performance.Costs_op.clip(lower=0) / era,
            label='Grid connection', width=width, color=cm['salmon_light'], edgecolor='black')

    ax.axhline(0, color='black', linewidth=0.8)

    ax.set_xticks(idx)
    ax.set_xticklabels(round(df_performance.Costs_inv / era, 1).values)

    plt.title(objectives[0] + "-" + objectives[1] + " Pareto : " + scenario)

    if objectives[0] == "CAPEX":
        obj_x = "CAPEX [CHF/m$^2$yr]"
    elif objectives[0] == "TOTEX":
        obj_x = "TOTEX [CHF/m$^2$yr]"

    if objectives[1] == "OPEX":
        obj_y = "[CHF/m$^2$yr]"
    elif objectives[1] == "GWP":
        obj_y = "GWP [kgkgCO2/m$^2$yr]"

    plt.xlabel(obj_x)
    plt.ylabel(obj_y)

    plt.legend(ncol=2)

    if save_fig:
        plt.tight_layout()
        plt.savefig((name_fig + '_' + scenario + '.' + format_fig), format=format_fig, dpi=300)

    plt.show()


def plot_gwp_KPIs(results, save_fig=False, name='GWP', format='png'):
    """
        Plot the GWP_Op, GWP_Constr and GWP_Tot
    """
    scenario = list(results.keys())[0]
    ids = list(results[scenario].keys())

    dict_df_perf = {}
    GWP_OP_list = []
    GWP_CONSTR_list = []
    GWP_TOT_list = []
    Cost_inv_list = []  # not necessary
    for id in ids:
        dict_df_perf.update({id: pd.DataFrame.from_dict(results[scenario][id]['df_Performance'])})
        GWP_OP_list.append(dict_df_perf[id].loc['Network', 'GWP_op'])
        GWP_CONSTR_list.append(dict_df_perf[id].loc['Network', 'GWP_constr'])
        GWP_TOT_list.append(dict_df_perf[id].loc['Network', 'GWP_op'] + dict_df_perf[id].loc['Network', 'GWP_constr'])
        Cost_inv_list.append(dict_df_perf[id].loc['Network', 'Costs_inv'])

    df = pd.DataFrame({'scenario': ids, 'GWP_Op': GWP_OP_list, 'GWP_Constr': GWP_CONSTR_list, 'GWP_Tot': GWP_TOT_list,
                       'Cost_Inv': Cost_inv_list})

    df.plot('scenario', y=['GWP_Op', 'GWP_Constr', 'GWP_Tot'], marker='.', linestyle='--')

    plt.xlabel('Scenario')
    plt.ylabel('GWP')
    # plt.legend(loc='upper center', bbox_to_anchor=(0.5, -0.20),
    #          fancybox=True, shadow=True, ncol=3)

    if save_fig:
        plt.tight_layout()
        plt.savefig((name + '.' + format), format=format, dpi=300)

    plt.show()


def plot_unit_size(results, units_to_plot):
    scenario = list(results.keys())[0]
    ids = list(results[scenario].keys())

    unit_dict = dict()
    for unit in units_to_plot:
        unit_dict[unit] = dict()
        for id in ids:
            idx = [unit in string for string in results[scenario][id]['df_Unit'].index]
            unit_dict[unit][id] = results[scenario][id]['df_Unit'][idx]['Units_Mult'].sum()
        unit_dict[unit] = pd.DataFrame.from_dict(unit_dict[unit], orient='index')

    fig, ax = plt.subplots()
    for key in unit_dict:
        ax.plot(ids, unit_dict[key].to_numpy(), marker='.', linestyle='-')

    plt.xlabel('Scenario [-]')
    plt.ylabel('Unit size [ref size]')

    plt.show()


def plot_profiles(df, units_to_plot, style='plotly', label='FR_long', color='ColorPastel', resolution='weekly',
                  save_fig=False, name='plot_profiles', format='png', plot_curtailment=False):
    if resolution == 'monthly':
        items_average = 730
    elif resolution == 'weekly':
        items_average = 168
    elif resolution == 'daily':
        items_average = 24
    else:
        items_average = 1

    units_demand = []
    units_supply = []
    for unit in units_to_plot:
        if unit == "PV":
            units_supply.append(unit)
        elif unit in ["Battery", "EV_district"]:
            units_demand.append(unit)
            units_supply.append(unit)
        else:
            units_demand.append(unit)

    # Grids
    import_elec = df['df_Grid_t'].xs(('Electricity', 'Network'), level=('Layer', 'Hub')).Grid_supply[:-2]
    export_elec = df['df_Grid_t'].xs(('Electricity', 'Network'), level=('Layer', 'Hub')).Grid_demand[:-2]
    ng = df['df_Grid_t'].xs(('NaturalGas', 'Network'), level=('Layer', 'Hub')).Grid_supply[:-2]

    import_profile = np.array([])
    export_profile = np.array([])
    ng_profile = np.array([])
    for i in range(1, 366):
        id = df['df_Index'].PeriodOfYear[i * 24]
        import_profile = np.concatenate((import_profile, import_elec.xs(id)))
        export_profile = np.concatenate((export_profile, export_elec.xs(id)))
        ng_profile = np.concatenate((ng_profile, ng.xs(id)))

    import_profile = moving_average(import_profile, items_average)
    export_profile = moving_average(export_profile, items_average)
    ng_profile = moving_average(ng_profile, items_average)

    # Units
    demands = dict()
    supplies = dict()
    curtailments = dict()
    for unit in units_to_plot:
        df_aggregated = df['df_Unit_t'][df['df_Unit_t'].index.get_level_values('Unit').str.contains(unit)]
        if unit in units_demand:
            demand = df_aggregated.droplevel('Layer').Units_demand[:-2].groupby(['Period', 'Time']).sum()
            demands[unit] = np.array([])
            for i in range(1, 366):
                t = df['df_Index'].PeriodOfYear[i * 24]
                demands[unit] = np.concatenate((demands[unit], demand.xs(t)))
        if unit in units_supply:
            supply = df_aggregated.droplevel('Layer').Units_supply[:-2].groupby(['Period', 'Time']).sum()
            supplies[unit] = np.array([])
            for i in range(1, 366):
                t = df['df_Index'].PeriodOfYear[i * 24]
                supplies[unit] = np.concatenate((supplies[unit], supply.xs(t)))
        if unit=='PV' and plot_curtailment:
            curtailment = df_aggregated.droplevel('Layer').Units_curtailment[:-2].groupby(['Period', 'Time']).sum()
            curtailments[unit] = np.array([])
            for i in range(1, 366):
                t = df['df_Index'].PeriodOfYear[i * 24]
                curtailments[unit] = np.concatenate((curtailments[unit], curtailment.xs(t)))


    for unit in units_demand:
        demands[unit] = moving_average(demands[unit], items_average)
    for unit in units_supply:
        supplies[unit] = moving_average(supplies[unit], items_average)
    if plot_curtailment:
        curtailments['PV'] = moving_average(curtailments['PV'], items_average)

    idx = list(range(1, len(list(demands.values())[0]) + 1))

    title = 'Energy profiles with a ' + resolution + ' moving average'
    obj_x = 'Time [hours]'
    obj_y = '[kWh]'

    if style == 'matplotlib':
        fig, ax = plt.subplots()
        ax.plot(idx, import_profile, color=layout.loc['Electrical_grid', color],
                label=layout.loc['Electrical_grid', label])
        ax.plot(idx, -export_profile, color=layout.loc['Electrical_grid_feed_in', color],
                label=layout.loc['Electrical_grid_feed_in', label])
        ax.plot(idx, ng_profile, color=layout.loc['NaturalGas', color], label=layout.loc['NaturalGas', label],
                alpha=0.5)
        for unit in units_demand:
            ax.plot(idx, demands[unit], linestyle='--', label=layout.loc[unit, label], color=layout.loc[unit, color])
        for unit in units_supply:
            ax.plot(idx, -supplies[unit], label=layout.loc[unit, label], color=layout.loc[unit, color])
        if plot_curtailment:
            ax.plot(idx, -curtailments['PV'], linestyle='.', label=layout.loc['Curtailment', label], color=layout.loc['Curtailment', color])

        ax.set_title(title)
        ax.set_xlabel(obj_x)
        ax.set_ylabel(obj_y)
        ax.legend(loc='best')

        if save_fig:
            plt.tight_layout()
            plt.savefig((name + '.' + format), format=format, dpi=300)

        plt.show()

    else:
        fig = go.Figure()

        fig.add_trace(go.Scatter(
            x=idx,
            y=import_profile,
            mode="lines",
            name=layout.loc['Electrical_grid', label],
            line=dict(color=layout.loc['Electrical_grid', color])
        ))

        if export_profile.any() > 0:
            fig.add_trace(go.Scatter(
                x=idx,
                y=-export_profile,
                mode="lines",
                name=layout.loc['Electrical_grid_feed_in', label],
                line=dict(color=layout.loc['Electrical_grid_feed_in', color], dash='dash')
            ))

        if ng_profile.any() > 0:
            fig.add_trace(go.Scatter(
                x=idx,
                y=ng_profile,
                mode="lines",
                name=layout.loc['NaturalGas', label],
                line=dict(color=layout.loc['NaturalGas', color])
            ))

        for unit in units_demand:
            if demands[unit].any() > 0:
                fig.add_trace(go.Scatter(
                    x=idx,
                    y=demands[unit],
                    mode="lines",
                    name=layout.loc[unit, label],
                    line=dict(color=layout.loc[unit, color])
                ))
        for unit in units_supply:
            if supplies[unit].any() > 0:
                fig.add_trace(go.Scatter(
                    x=idx,
                    y=-supplies[unit],
                    mode="lines",
                    name=layout.loc[unit, label],
                    line=dict(color=layout.loc[unit, color], dash='dash')
                ))
        if plot_curtailment:
            fig.add_trace(go.Scatter(
                x=idx,
                y=-curtailments['PV'],
                mode="lines",
                name=layout.loc['Curtailment', label],
                line=dict(color=layout.loc['Curtailment', color], dash='dot')
            ))

        fig.update_layout(
            title_text=title,
            xaxis_title=obj_x,
            yaxis_title=obj_y,
            font=dict(
                size=16,
            )
        )

        fig.show()


def plot_resources(results, label='FR_long', color='ColorPastel',
                   save_path="", filename=None, export_format='html', auto_open=False):

    scenarios = list(results.keys())
    df_annuals = dict_to_df(results, 'df_Annuals')
    pareto_id = list(results[scenarios[0]].keys())[0]
    df_annuals = df_annuals.loc[(slice(None), pareto_id, slice(None), 'Network')]
    idx = df_annuals.index.levels[1].tolist()
    layers = ['NaturalGas', 'Oil', 'Electricity', 'Wood', 'Data']
    df_resources = pd.DataFrame(0, index=['NaturalGas', 'Oil', 'Electrical_grid', 'Wood', ], columns=['scenario', 'Supply'])
    df_resources = df_resources.merge(layout, left_index=True, right_on='Name')
    df_resources = df_resources.rename({'Electrical_grid': 'Electricity'})
    for scn in scenarios:
        df_resources.loc[:, ['scenario', 'Supply']] = [scn, df_annuals.loc[scn]['Supply_MWh']]
    df_resources.fillna(0, inplace=True)
    df_resources.reset_index(inplace=True)
    fig = go.Figure()
    for i, layer in enumerate(layers):
        df_to_plot = df_resources[df_resources['Name'] == layer]
        if ~df_to_plot.empty:
            fig.add_trace(
                go.Bar(x=df_to_plot['scenario'], y=df_to_plot['Supply'], name=df_to_plot.iloc[0][label],
                       marker=dict(color=df_to_plot[color]),
                       hovertemplate='<b>' + df_to_plot[label] + '</b>' +
                                     '<br>%{y:.2f} MWh'
                       )
                          )
    fig.update_layout(
        barmode="group",
        template='plotly_white',
        yaxis=dict(title="MWh"),
    )

    if filename is not None:
        filename = os.path.join(save_path, str(filename + '.' + export_format))
        if export_format == 'html':
            fig.to_html(filename)
        elif export_format == 'png':
            fig.to_image(filename)
    if auto_open:
        fig.show()


def monthly_heat_balance(df_results):
    """
        return data to plot a monthly heat balance of the df_results
        TODO : check if multi-building is okay

        Author : Florent

        Parameters:
            df_results (df): dataframe of a scenario

        Returns:
            df series of House_Q_heating, -House_Q_cooling, House_Q_convection, HeatGains, SolarGains
    """
    # Extract the data
    df_external = df_results['df_External']
    df_buildings_th_feature = df_results['df_Buildings'][['U_h', 'ERA']]
    df_buildings_t = df_results['df_Buildings_t']
    df_period_time = df_buildings_t.xs('Building1').index[:-2]

    # Prepare the df to store the heat flux
    list_columns = ['House_Q_heating', 'House_Q_cooling', 'House_Q_convection', 'HeatGains', 'SolarGains']
    df_heat_building_t = pd.DataFrame(0,
                                      index=df_period_time,
                                      columns=list_columns)
    # list of the two last periods used for design purpose to drop later
    period_to_drop = list(df_buildings_t.xs('Building1').index.get_level_values('Period').unique()[-2:])

    # For each building: calculation of the heat flux
    # and addition of the flux of each building in df_heat_building_t
    for b in list(df_buildings_th_feature.index):
        df_Q_convection_calcul = df_buildings_t.xs(b).merge(df_external, left_index=True, right_index=True)
        for i in period_to_drop:
            df_Q_convection_calcul = df_Q_convection_calcul.drop(i, level='Period')
        df_Q_convection_calcul['House_Q_convection'] = df_buildings_th_feature.loc[b, 'U_h'] * \
                                                       df_buildings_th_feature.loc[b, 'ERA'] * \
                                                       (df_Q_convection_calcul.T_ext - df_Q_convection_calcul.T_in)
        df_Q_convection_calcul = df_Q_convection_calcul[list_columns]
        df_heat_building_t = df_heat_building_t.add(df_Q_convection_calcul)

    # Monthly average (hypothèse, 1 month: 730 hours)
    House_Q_heating = np.array([])
    House_Q_cooling = np.array([])
    House_Q_convection = np.array([])
    HeatGains = np.array([])
    SolarGains = np.array([])

    for i in range(1, 366):
        id = df_results['df_Index'].PeriodOfYear[i * 24]
        data_id = df_heat_building_t.xs(id)
        House_Q_heating = np.concatenate((House_Q_heating, data_id.House_Q_heating))
        House_Q_cooling = np.concatenate((House_Q_cooling, data_id.House_Q_cooling))
        House_Q_convection = np.concatenate((House_Q_convection, data_id.House_Q_convection))
        HeatGains = np.concatenate((HeatGains, data_id.HeatGains))
        SolarGains = np.concatenate((SolarGains, data_id.SolarGains))

    items_average = 730

    House_Q_heating = np.sum(House_Q_heating.reshape(-1, items_average), axis=1)
    House_Q_cooling = np.sum(House_Q_cooling.reshape(-1, items_average), axis=1)
    House_Q_convection = np.sum(House_Q_convection.reshape(-1, items_average), axis=1)
    HeatGains = np.sum(HeatGains.reshape(-1, items_average), axis=1)
    SolarGains = np.sum(SolarGains.reshape(-1, items_average), axis=1)

    # ! - for House_Q_cooling to get negative values for cooling
    return House_Q_heating, -House_Q_cooling, House_Q_convection, HeatGains, SolarGains


def sunburst_eud(results, label='FR_long', save_path="", filename=None, export_format='html', auto_open=False):
    """
    :param results: dictionary from REHO results pickle
    :param label: indicates the labels to use and so the language. Pick among 'FR_long', 'FR_short',
     'EN_long', 'EN_short'
    :param save_path: directory to which the plot is to be saved
    :param filename: name of the plot
    :param export_format: can be either html or png
    :param auto_open: if export_format is html, to open it automatically in your browser
    :return: p, a plot that can be show
    """
    def add_class(row):
        ratio = [float(s) for s in str(row['ratio']).split("/")]
        class_ = row['id_class'].split("/")
        serie = pd.Series(ratio, index=class_).groupby(level=0).sum()
        for key, value in correspondance_dict.items():
            data_to_plot[value].update(data_to_plot[value] + serie * row[key])

    correspondance_dict = {'ERA': 'area_per_class',
                           'energy_heating_signature_kWh_y': 'sh_per_class',
                           'energy_hotwater_signature_kWh_y': 'dhw_per_class',
                           'energy_el_kWh_y': 'elec_per_class'}
    classes = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI', 'XII', 'XIII']
    df_buildings = dict_to_df(results, 'df_Buildings')
    data_to_plot = pd.DataFrame(0, index=classes, columns=['area_per_class', 'sh_per_class', 'dhw_per_class',
                                                           'elec_per_class'])
    class_names = pd.read_csv(os.path.join(path_to_plotting, 'sia380_1.csv'), index_col='id_class', sep=";")
    data_to_plot = data_to_plot.merge(class_names, left_index=True, right_on='id_class')

    if 'FR' in label.upper().split("_"):
        hover_text = 'Demande en énergie'
        liaison = ' du '
    else:
        hover_text = 'End Use Demand'
        liaison = ' of '

    scenarios = results.keys()
    for scn in scenarios:
        df_buildings.loc[(scn, list(results[scn].keys()))[0]].apply(add_class, axis=1)
        child_name = []
        parents_name = []
        text_template = []
        hover_template = []
        values_sun = []
        for i in range(len(classes)):
            [child_name.append(element) for element in [data_to_plot.iloc[i]['class_' + label], "SH", "DHW", "Elec"]]
            [parents_name.append(element) for element in
             ["Total", data_to_plot.iloc[i]['class_' + label], data_to_plot.iloc[i]['class_' + label],
              data_to_plot.iloc[i]['class_' + label]]]
            [values_sun.append(element) for element in [
                data_to_plot.iloc[i]['sh_per_class'] + data_to_plot.iloc[i]['dhw_per_class'] +
                data_to_plot.iloc[i]['elec_per_class'],
                data_to_plot.iloc[i]['sh_per_class'], data_to_plot.iloc[i]['dhw_per_class'],
                data_to_plot.iloc[i]['elec_per_class']]]
            [text_template.append(element) for element in ['%{label}<br>%{percentParent:.2%}',
                                                           '%{label}<br>%{percentParent:.2%}',
                                                           '%{label}<br>%{percentParent:.2%}',
                                                           '%{label}<br>%{percentParent:.2%}']]
            [hover_template.append(element) for element in ['<i>%{label}</i><br><b>' + hover_text + ': </b>%{value} kWh<br>%{percentParent:.2%}' + liaison + '%{parent}',
                                                            '<i>%{label}</i><br><b>' + hover_text + ': </b>%{value} kWh<br>%{percentRoot:.2%}' + liaison + '%{root}',
                                                            '<i>%{label}</i><br><b>' + hover_text + ': </b>%{value} kWh<br>%{percentRoot:.2%}' + liaison + '%{root}',
                                                            '<i>%{label}</i><br><b>' + hover_text + ': </b>%{value} kWh<br>%{percentRoot:.2%}' + liaison + '%{root}']]

        values_sun = [round(val, 2) for val in values_sun]
        fig = go.Figure(go.Sunburst(
                          labels=child_name,
                          parents=parents_name,
                          values=values_sun,
                          branchvalues='total',
                          name=hover_text,
                          hovertemplate=hover_template,
                          texttemplate=text_template,
                          ))

        fig.update_layout(
            sunburstcolorway=["#413D3A", "#CAC7C7", "#B51F1F", "#007480", "#00A79F", "#FEA993"],
            extendsunburstcolors=True)
        if filename is not None:
            filename = os.path.join(save_path, str(scn) + "_" + filename + '_sunburst.')
            if export_format == 'png':
                fig.write_image(filename + export_format)
            elif export_format == 'html':
                fig.write_html(filename + export_format)
            return print("Sunburt printed at " + filename + export_format)

        if auto_open:
            return fig



def temperature_profile(df_results):
    """
        return a df series of the Tin temperature profile
        one column per building
        TODO : check if multi-building is okay

        Author : Florent

        Parameters:
            df_results (df): dataframe of a scenario

        Returns:
            df_Tin
    """
    # Extract the data
    buildings_list = list(df_results['df_Buildings'].index)
    df_buildings_t = df_results['df_Buildings_t']

    # Prepare the df to store the Tin
    df_Tin = pd.DataFrame()

    # list of the two last periods used for design purpose to drop later
    period_to_drop = list(df_buildings_t.xs('Building1').index.get_level_values('Period').unique()[-2:])

    # For each building: calculation of the Tin series
    for b in buildings_list:
        # Take Tin for the building in df_buildings_t
        df_Tin_building = pd.DataFrame()
        df_Tin_building['T_in'] = df_buildings_t.xs(b)['T_in']

        # drop the last two periods for design
        for i in period_to_drop:
            df_Tin_building = df_Tin_building.drop(i, level='Period')

        # to averaging over days if wanted
        items_average = 24  # daily
        # array to work for a building
        Tin_building = np.array([])

        for j in range(1, 366):
            id = df_results['df_Index'].PeriodOfYear[j * 24]
            data_id = df_Tin_building.xs(id)
            Tin_building = np.concatenate((Tin_building, data_id['T_in']))

        # to averaging over days if wanted
        # Tin_building = np.mean(Tin_building.reshape(-1, items_average), axis=1)

        # Store the data in df_Tin (one col per building)
        df_Tin['T_in_' + str(b)] = Tin_building

    # create idx
    idx = list(df_Tin.index + 1)
    return df_Tin.to_numpy(), idx


def plot_EUD_FES(results):
    scenario = list(results.keys())[0]

    df_annuals = results[scenario][0]['df_Annuals']

    # service end use
    df_EUD_FEC = pd.DataFrame(0,
                              index=['Electricity_EUD', 'Electricity_FEC', 'SH_EUD', 'SH_FEC', 'DHW_EUD', 'DHW_FEC'],
                              columns=['Electrical grid', 'Electrical appliances', 'Oil boiler (oil)',
                                       'Oil boiler (heat)'])

    # Oil per service
    oil_for_oil_boiler = df_annuals.loc[('Oil', 'OIL_Boiler_Building1'), 'Demand_MWh']
    DHW_from_oil_boiler = df_annuals.loc[('DHW', 'OIL_Boiler_Building1'), 'Supply_MWh']
    SH_from_oil_boiler = df_annuals.loc[('SH', 'OIL_Boiler_Building1'), 'Supply_MWh']
    ratio_SHonDHW_oil_boiler = SH_from_oil_boiler / (DHW_from_oil_boiler + SH_from_oil_boiler)

    df_EUD_FEC.loc['Electricity_EUD', 'Electrical grid'] = df_annuals.loc[('Electricity', 'Network'), 'Supply_MWh']
    df_EUD_FEC.loc['Electricity_FEC', 'Electrical appliances'] = df_annuals.loc[
        ('Electricity', 'Building1'), 'Demand_MWh']
    df_EUD_FEC.loc['SH_EUD', 'Oil boiler (heat)'] = df_annuals.loc[('SH', 'OIL_Boiler_Building1'), 'Supply_MWh']
    df_EUD_FEC.loc['SH_FEC', 'Oil boiler (oil)'] = ratio_SHonDHW_oil_boiler * df_annuals.loc[
        ('Oil', 'OIL_Boiler_Building1'), 'Demand_MWh']
    df_EUD_FEC.loc['DHW_EUD', 'Oil boiler (heat)'] = df_annuals.loc[('DHW', 'OIL_Boiler_Building1'), 'Supply_MWh']
    df_EUD_FEC.loc['DHW_FEC', 'Oil boiler (oil)'] = (1 - ratio_SHonDHW_oil_boiler) * df_annuals.loc[
        ('Oil', 'OIL_Boiler_Building1'), 'Demand_MWh']

    print(df_EUD_FEC)
