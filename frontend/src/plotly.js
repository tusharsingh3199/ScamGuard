import Plotly from 'plotly.js/lib/core';
import Bar from 'plotly.js/lib/bar';
import Sankey from 'plotly.js/lib/sankey';
import Scatter from 'plotly.js/lib/scatter';
import createPlotlyComponent from 'react-plotly.js/factory';

Plotly.register([Bar, Sankey, Scatter]);

export default createPlotlyComponent(Plotly);