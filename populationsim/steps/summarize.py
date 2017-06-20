# PopulationSim
# See full license in LICENSE.txt.

import logging

import orca
import pandas as pd
import numpy as np

from helper import get_control_table
from helper import get_weight_table
from populationsim.util import setting

logger = logging.getLogger(__name__)


def summarize_geography(geography, weight_col,
                        crosswalk_df, results_df, incidence_df):

    # controls_table for current geography level
    controls_df = get_control_table(geography)
    control_names = controls_df.columns.tolist()

    zone_ids = crosswalk_df[geography].unique()

    results = []
    controls = []
    for zone_id in zone_ids:

        zone_controls = controls_df.loc[zone_id].tolist()
        controls.append(zone_controls)

        zone_row_map = results_df[geography] == zone_id
        zone_weights = results_df[zone_row_map]

        incidence = incidence_df.loc[zone_weights.hh_id]

        weights = zone_weights[weight_col].tolist()
        x = [(incidence[c] * weights).sum() for c in control_names]
        results.append(x)

    controls_df = pd.DataFrame(
        data=np.asanyarray(controls),
        columns=['%s_control' % c for c in control_names],
        index=zone_ids
    )

    summary_df = pd.DataFrame(
        data=np.asanyarray(results),
        columns=['%s_result' % c for c in control_names],
        index=zone_ids
    )

    dif_df = pd.DataFrame(
        data=np.asanyarray(results) - np.asanyarray(controls),
        columns=['%s_diff' % c for c in control_names],
        index=zone_ids
    )

    summary_df = pd.concat([controls_df, summary_df, dif_df], axis=1)

    summary_cols = summary_df.columns.tolist()

    summary_df['geography'] = geography
    summary_df['id'] = summary_df.index
    summary_df.index = summary_df['geography'] + '_' + summary_df['id'].astype(str)
    summary_df = summary_df[['geography', 'id'] + summary_cols]

    return summary_df


def meta_summary(incidence_df, control_spec, top_geography, top_id, sub_geographies):

    incidence_df = incidence_df[incidence_df[top_geography] == top_id]

    control_cols = control_spec.target.values

    controls_df = get_control_table(top_geography)

    # controls for this geography as series
    controls = controls_df[control_cols].loc[top_id]

    seed_weight_cols = ['initial_seed_weight', 'final_seed_weight', 'integer_seed_weight']
    incidence = incidence_df[control_cols]

    summary = pd.DataFrame(index=control_cols)
    summary['control'] = controls
    for c in seed_weight_cols:
        if c in incidence_df:
            summary[c] = incidence.multiply(incidence_df[c], axis="index").sum(axis=0)

    for g in sub_geographies:

        sub_weight_cols = ['balanced_weight', 'integer_weight']

        sub_weights = get_weight_table(g)

        if sub_weights is None:
            continue

        sub_weights = sub_weights[sub_weights[top_geography] == top_id]

        sub_weights = sub_weights[['hh_id'] + sub_weight_cols].groupby('hh_id').sum()

        for c in sub_weight_cols:
            summary['%s_%s' % (g, c)] = incidence.multiply(sub_weights[c], axis="index").sum(axis=0)

    return summary


@orca.step()
def summarize(crosswalk, incidence_table, control_spec):

    crosswalk_df = crosswalk.to_frame()
    incidence_df = incidence_table.to_frame()

    geographies = setting('geographies')
    seed_geography = setting('seed_geography')
    meta_geography = geographies[0]
    sub_geographies = geographies[geographies.index(seed_geography) + 1:]
    household_id_col = setting('household_id_col')

    meta_ids = crosswalk_df[meta_geography].unique()
    for meta_id in meta_ids:
        meta_summary_df = \
            meta_summary(incidence_df, control_spec, meta_geography, meta_id, sub_geographies)
        orca.add_table('%s_%s_summary' % (meta_geography, meta_id), meta_summary_df)

    hh_weights_summary = incidence_df[['final_seed_weight', 'integer_seed_weight']].copy()

    for geography in sub_geographies:

        weights_df = get_weight_table(geography)

        if weights_df is None:
            continue

        hh_weight_cols = [household_id_col, 'balanced_weight', 'integer_weight']
        hh_weights = weights_df[hh_weight_cols].groupby([household_id_col]).sum()
        hh_weights_summary['%s_balanced_weight' % geography] = hh_weights['balanced_weight']
        hh_weights_summary['%s_integer_weight' % geography] = hh_weights['integer_weight']

        # aggregate to seed level
        hh_id_col = incidence_df.index.name
        aggegrate_weights = weights_df.groupby([seed_geography, hh_id_col], as_index=False).sum()
        aggegrate_weights.set_index(hh_id_col, inplace=True)

        aggegrate_weights = aggegrate_weights[[seed_geography, 'balanced_weight', 'integer_weight']]
        aggegrate_weights['sample_weight'] = incidence_df['sample_weight']
        aggegrate_weights['initial_seed_weight'] = incidence_df['initial_seed_weight']
        aggegrate_weights['final_seed_weight'] = incidence_df['final_seed_weight']
        aggegrate_weights['integer_seed_weight'] = incidence_df['integer_seed_weight']

        orca.add_table('%s_aggregate' % (geography,), aggegrate_weights)

        df = summarize_geography(seed_geography, 'integer_weight',
                                 crosswalk_df, weights_df, incidence_df)
        orca.add_table('%s_%s_summary' % (geography, seed_geography,), df)

        df = summarize_geography(geography, 'integer_weight',
                                 crosswalk_df, weights_df, incidence_df)
        orca.add_table('%s_summary' % (geography,), df)

    orca.add_table('hh_weights_summary', hh_weights_summary)