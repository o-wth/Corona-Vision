let CONFIRMED_IX = 0;
let DEATHS_IX = 1;
let RECOVERED_IX = 2;
let ACTIVE_IX = 3;

let CHART_OPTIONS = {
    country: "",
    province: "",
    admin2: "",
    scale_type: "linear",
    chart_type: "total",
    chart: null,
    reload_function: reload_chart
};

function download_canvas() {
	let url = $("#chart")[0].toDataURL("image/png;base64");
	let filename = 'COVID19_Chart';
	if (country) filename += `_${country}`;
	if (province) filename += `_${province}`;
	if (admin2) filename += `_${admin2}`;
	filename += '.png';

	$("#download-chart")[0].href = url;
	$("#download-chart")[0].setAttribute("download", filename);
	$("#download-chart")[0].click();
}

function init_chart() {
	init_chart_options();
	reload_chart();
}

function init_chart_options() {
    let chart = CHART_OPTIONS.chart;

    $("select[name=scale-type]").change(
        function() {
            if (this.value == 'logarithmic' || this.value == 'linear') {
                CHART_OPTIONS.scale_type = this.value;
                chart.options.scales.yAxes[0].type = this.value;
                chart.update();
            }
        }
    );

    $("select[name=chart-type]").change(
        function() {
            CHART_OPTIONS.chart_type = this.value;
            CHART_OPTIONS.reload_function();
        }
    );

    $("input[name=display-confirmed]").change(
        function() {
            chart.data.datasets[CONFIRMED_IX].hidden = !this.checked;
            chart.update();
        }
    );

    $("input[name=display-deaths]").change(
        function() {
            chart.data.datasets[DEATHS_IX].hidden = !this.checked;
            chart.update();
        }
    );

    $("input[name=display-recovered]").change(
        function() {
            chart.data.datasets[RECOVERED_IX].hidden = !this.checked;
            chart.update();
        }
    );

    $("input[name=display-active]").change(
        function() {
            chart.data.datasets[ACTIVE_IX].hidden = !this.checked;
            chart.update();
        }
    );
}

function new_chart(canvas_id) {
	let data = {
		labels: [],
		datasets: [
			{
				label: 'Confirmed cases',
				backgroundColor: 'yellow',
				borderColor: 'yellow',
				fill: false,
				data: [],
				lineTension: 0
			},
			{
				label: 'Deaths',
				backgroundColor: 'red',
				borderColor: 'red',
				fill: false,
				data: [],
				lineTension: 0
			},
			{
				label: 'Recovered',
				backgroundColor: 'green',
				borderColor: 'green',
				fill: false,
				data: [],
				lineTension: 0
			},
			{
				label: 'Active',
				backgroundColor: 'orange',
				borderColor: 'orange',
				fill: false,
				data: [],
				lineTension: 0,
				hidden: true
			}
		]
	};
	return new Chart(get_canvas(canvas_id), {
		type: 'line',
		data: data,
		options: {
			responsive: true,
			title: {
				display: true,
				text: "Cases",
				fontColor: "#f5f5f5",
				fontSize: 30,
				fontStyle: "",
				fontFamily: "Lato"
			},
			legend: {
				display: true,
				labels: {
					fontColor: "#f5f5f5"
				}
			},
			hover: {
				mode: 'nearest',
				intersect: true
			},
			scales: {
				xAxes: [
					{
						gridLines: {
							color: "#f5f5f5"
						},
						ticks: {
							fontColor: "#f5f5f5"
						}
					}
				],
				yAxes: [
					{
						gridLines: {
							color: "#f5f5f5"
						},
						ticks: {
							fontColor: "#f5f5f5"
						}
					}
				]
			}
		}
	});
}

function get_canvas(a) {
	return document.getElementById(a).getContext('2d');
}

function reset_chart() {
	let chart = CHART_OPTIONS.chart;
	chart.options.title.text = 'Cases';
	chart.data.labels = [];
	for (let i = 0; i < chart.data.datasets.length; i++) {
		chart.data.datasets[i].data = [];
	}
	chart.update();
}

function add_chart_data(data) {
	reset_chart();
	let chart = CHART_OPTIONS.chart;
	for (let total of data) {
		chart.data.labels.push(total.entry_date);
		let datasets = chart.data.datasets;
		if (CHART_OPTIONS.chart_type == 'total') {
			datasets[CONFIRMED_IX].data.push(total.confirmed);
			datasets[DEATHS_IX].data.push(total.deaths);
			datasets[RECOVERED_IX].data.push(total.recovered);
			datasets[ACTIVE_IX].data.push(total.active);
		} else if (CHART_OPTIONS.chart_type == 'daily-change') {
			datasets[CONFIRMED_IX].data.push(total.dconfirmed);
			datasets[DEATHS_IX].data.push(total.ddeaths);
			datasets[RECOVERED_IX].data.push(total.drecovered);
			datasets[ACTIVE_IX].data.push(total.dactive);
		}
	}
	chart.update()
}

function reload_chart() {
	reset_chart();
	
	let country = CHART_OPTIONS.country;
	let province = CHART_OPTIONS.province;
	let admin2 = CHART_OPTIONS.admin2;
	
	let label = generate_name(country, province, admin2);

	let chart = CHART_OPTIONS.chart;

	let params = {
		country: country,
		province: province,
		admin2: admin2,
		world: "World"
	}
	
	$.getJSON(
		"/cases/totals_sequence",
		params,
		function(data) {
			add_chart_data(data);
			chart.options.title.text = 'Cases in: ' + label;
			chart.update();
		}
	)
}