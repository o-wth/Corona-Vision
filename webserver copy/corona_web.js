const express = require('express');
const bodyparser = require('body-parser');
const fs = require('fs');

const Handlebars = require('hbs');
const corona_sql = require('./corona_sql');
const sqlstring = require('sqlstring');
const NewsAPI = require('newsapi');

const newsapi = new NewsAPI(process.env.NEWS_API_KEY);

const datatables = require('./corona_datatable_back');

/* Register the "partials" - handlebars templates that can be included in other templates */
Handlebars.registerPartial("navbar", fs.readFileSync("views/navbar.hbs", "utf-8"));
Handlebars.registerPartial("styles", fs.readFileSync("views/styles.hbs", "utf-8"));
Handlebars.registerPartial("selectors", fs.readFileSync("views/selectors.hbs", "utf-8"));
Handlebars.registerPartial("chart_options", fs.readFileSync("views/chart_options.hbs", "utf-8"));
// Handlebars.registerPartial("map_panel", fs.readFileSync("views/map_panel.hbs", "utf-8"));

app = express();

/* Static data url */
app.use(express.static('static'));

/* For POST request body */
app.use(bodyparser.urlencoded({
    extended: true
}));

/* Use Handlebars */
app.set('view engine', 'hbs');

/* Main Page
 * The Main Page includes charts, data tables, and live stats */
let last_update = null;
app.get("/", (req, res) => {
    if (last_update == null || (Date.now() - last_update > 60000)) {
        get_sql("select MAX(update_time) as update_time from datapoints;").then(
            data => {
                last_update = data[0]['update_time'];
                res.render("main_page", {last_update: datatables.format_update_time(last_update)});
            }
        ).catch(
            err => {
                res.render("main_page", {last_update: "Recently"});
                console.err("Error during update time selection")
            }
        );
    } else {
        res.render("main_page", {last_update: datatables.format_update_time(last_update)});
    }
});

/* Chart Page
 * The Chart Page includes customizable chart with LSTM and Logistic predictions */
app.get("/charts", (req, res) => {
    res.render("charts");
});

/* Technical info about the charts */
app.get("/charts_info", (req, res) => {
    res.render("charts_info");
});

/* Map Page
 * The Map Page includes a map of the most recent cases, to the state level. */
app.get("/map", (req, res) => {
    res.render("map");
});

/* Totals Table (backend)
 * Provides an HTML table that can be inserted into the main page */
app.get("/cases/totals_table", (req, res) => {
    let params = req.query;

    // get location and date
    let admin0 = get(params, "admin0") || "";
    let admin1 = get(params, "admin1") || "";
    let admin2 = get(params, "admin2") || "";
    let entry_date = get(params, "date") || "live";

    let query = "select * from datapoints";
    
    // dont filter if the field = 'all'
    let where_conds = [];
    if (admin0 != 'all') where_conds.push("admin0 = " + sqlstring.escape(admin0));
    if (admin1 != 'all') where_conds.push("admin1 = " + sqlstring.escape(admin1));
    if (admin2 != 'all') where_conds.push("admin2 = " + sqlstring.escape(admin2));

    if (where_conds.length > 0) {
        query += " where " + where_conds.join(" and ");
    }

    query += " and entry_date = " + sqlstring.escape(entry_date);

    get_sql(query, key="table_" + query).then(
        content => {
            res.send(datatables.make_rows(content, admin0, admin1, admin2));
        }
    );
});

/* Totals API
 * This provides results for a given admin0, admin1, or admin2 */
app.get("/cases/totals", (req, res) => {
    let params = req.query;

    // get location and date
    let admin0 = get(params, "admin0") || "";
    let admin1 = get(params, "admin1") || "";
    let admin2 = get(params, "admin2") || "";
    let entry_date = get(params, "date") || "live";

    let query = "select * from datapoints";
    
    // dont filter if the field = 'all'
    let where_conds = [];
    if (admin0 != 'all') where_conds.push("admin0 = " + sqlstring.escape(admin0));
    if (admin1 != 'all') where_conds.push("admin1 = " + sqlstring.escape(admin1));
    if (admin2 != 'all') where_conds.push("admin2 = " + sqlstring.escape(admin2));

    if (where_conds.length > 0) {
        query += " where " + where_conds.join(" and ");
    }

    query += " and entry_date = " + sqlstring.escape(entry_date);

    get_sql(query).then(
        content => res.send(JSON.stringify(content))
    );
});

function utc_iso(date) {
    let year = date.getUTCFullYear();
    let month = `${date.getUTCMonth() + 1}`;
    let day = `${date.getUTCDate()}`;
    month = month.padStart(2, "0");
    day = day.padStart(2, "0");
    return year + "-" + month + "-" + day;
}

/* Totals Sequence API
 * Gives the most recent data, with missing dates __not__ filled in (yet) */
app.get("/cases/totals_sequence", (req, res) => {
    let params = req.query;

    // get location and date
    let admin0 = get(params, "admin0") || "";
    let admin1 = get(params, "admin1") || "";
    let admin2 = get(params, "admin2") || "";

    let query = "select * from datapoints";
    
    // dont filter if the field = 'all'
    let where_conds = [];
    if (admin0 != 'all') where_conds.push("admin0 = " + sqlstring.escape(admin0));
    if (admin1 != 'all') where_conds.push("admin1 = " + sqlstring.escape(admin1));
    if (admin2 != 'all') where_conds.push("admin2 = " + sqlstring.escape(admin2));

    if (where_conds.length > 0) {
        query += " where " + where_conds.join(" and ");
    }

    query += " order by entry_date";

    get_sql(query).then(
        (content) => {
            let labels = ['total', 'recovered', 'deaths', 'active'];
            let resp = {};
            
            resp.entry_date = [];
            for (let label of labels) {
                resp[label] = [];
            }
            
            /* !!! This strongly relies on the date format !!! */
            let day = new Date(content[0].entry_date);
            let last_day = new Date(content[content.length - 1].entry_date);

            let i = 0;
            // <, NOT <=, because the most recent day's data is incomplete
            while (day < last_day) {
                resp.entry_date.push(utc_iso(day));
                for (let label of labels) {
                    resp[label].push(content[i][label]);
                }

                // we don't increment the data index if the next date isn't found
                day.setUTCDate(day.getUTCDate() + 1);
                if (i + 1 < content.length) {
                    let content_iso = utc_iso(new Date(content[i + 1].entry_date));
                    if (utc_iso(day) == content_iso) i += 1;
                }
            }
            
            let daily_changes = {};
            for (let label of labels) {
                let daily_label = "d" + label;
                let last_val = 0;
                daily_changes[daily_label] = [];
                for (let i = 0; i < resp[label].length; i++) {
                    let this_val = resp[label][i];
                    daily_changes[daily_label].push(this_val - last_val)
                    last_val = this_val;
                }
            }

            res.json({...resp, ...daily_changes});
        }
    );

});

/* Countries API - returns a list of all countries for a given date */
app.get("/list/countries", (req, res) => {
    let params = req.query;
    let entry_date = get(params, "date") || "live";

    // base query
    let query = "select distinct admin0 from datapoints where admin0 != '' and entry_date = " + sqlstring.escape(entry_date);

    // require a admin1 if necessary
    if ("need_admin1" in params && params.need_admin1 == 1) { query += " and admin1 != ''"; }

    // alphabetical order
    query += " order by admin0";

    get_sql(query).then(
        content => {
            res.json(content);
        }
    );
});

/* Provinces API - gives a list of admin1s for a given admin0 and date */
app.get("/list/provinces", (req, res) => {
    let params = req.query;

    // require the admin0
    if (!("admin0" in params)) res.end();

    // base query
    let query = sqlstring.format("select distinct admin1 from datapoints where admin0 = ? and admin1 != ''" , params.admin0);

    // require a admin2 if necessary
    if ("need_admin2" in params && params.need_admin2 == 1) { query += " and admin2 != ''"; }
    
    // alphabetical order
    query += " order by admin1";

    get_sql(query).then(
        content => res.json(content)
    );
});

/* County API - gives a list of counties for a given admin0, admin1, and date */
app.get("/list/admin2", (req, res) => {
    let params = req.query;

    // require the admin0 and admin1
    if (!("admin0" in params) || !("admin1" in params)) res.end();

    // base query
    let query = sqlstring.format("select distinct admin2 from datapoints where admin0 = ? and admin1 = ? and admin2 != '' order by admin2", [params.admin0, params.admin1]);
    
    get_sql(query).then(
        content => res.json(content)
    );
});

/* Dates API - list all dates that we have on record */
app.get("/list/dates", (req, res) => {
    let query = "select distinct entry_date from datapoints order by entry_date desc";

    get_sql(query).then(
        content => res.json(content)
    );
});

/* First Days API - returns the stats for each admin0 on the first day of infection */
app.get("/cases/first_days", (req, res) => {
    let query = sqlstring.format("select * from datapoints where is_first_day = true order by entry_date;");
    get_sql(query).then(
        content => res.json(content)
    );
});

/* Cases-by-date API - returns all cases (with a labelled location) for a given date. Used by the map */
app.get("/cases/date", (req, res) => {
    let entry_date = get(req.query, "date") || "live";
    let query = sqlstring.format("select * from datapoints where entry_date = ? and latitude != 0 and longitude != 0 and admin2 = '' and admin0 != ''", entry_date);
    get_sql(query).then( 
        content => res.json(content)
    );
});

geojson_cache = {};
geojson_max_age = 1000 * 60 * 15; // 15-minute caching
app.get("/geojson", (req, res) => {
    let entry_date = req.query['date'] || new Date().toISOString().substring(0, 10);
    let query = sqlstring.format("select * from datapoints where entry_date = ? and latitude is not null and longitude is not null and admin2 = '' and admin0 != '' and total > 10", entry_date);
    if (query in geojson_cache) {
        let {data, update_time} = geojson_cache[query];
        if (Date.now() - update_time < geojson_max_age) {
            res.json(data);
            return;
        }
    }

    get_sql(query).then(
        content => {
            let geojson_result = geojson(content);
            geojson_cache[query] = {data: geojson_result, update_time: Date.now()};
            res.json(geojson_result);
        }
    );
});

function geojson(content) {
    let feature_list = [];
    for (let datapoint of content) {
        let name = datapoint.admin0 || "World";
        if (datapoint.admin1) name = datapoint.admin1 + ", " + name;
        if (datapoint.admin2) name = datapoint.admin2 + ", " + name;
        feature_list.push({
            id: name,
            type: "Feature",
            properties: {
                name: name,
                ...datapoint
            },
            geometry: {
                coordinates: [datapoint.longitude, datapoint.latitude],
                type: 'Point'
            }
        });
    }
    return {
        type: "FeatureCollection",
        features: feature_list
    };

}

/* What To Do Page - gives information about how to make homemade masks, general social distancing tips,
 * and organizations that you can donate to to help healthcare workers. */
app.get("/whattodo", (req, res) => {
    res.render("whattodo");
});

function removeDuplicateArticles(articles) {
    let seen_urls = {};
    let new_articles = [];
    for (let article of articles) {
        if (!(article.url in seen_urls)) {
            new_articles.push(article);
            seen_urls[article.url] = 1;
        }
    }
    return new_articles;
}

/* Recent Page - recent news about COVID-19 from the News API */
let recent_news = {};
app.get("/news", (req, res) => {
    let possible_categories = ['business', 'entertainment', 'general', 'health', 'science', 'sports', 'technology'];
    let category = req.query['category'] || "general";
    if (!possible_categories.includes(category)) {
        category = "general";
    }

    /* 1000 ms/s * 60 s/m * 60 m/h * 1 h --> 1 hour cache age */
    let newsCacheExists = category in recent_news;
    if (newsCacheExists) {
        let newsCacheShouldBeUpdated = Date.now() - recent_news[category].update_time > 1000 * 60 * 60 * 1;
        if (!newsCacheShouldBeUpdated) {
            res.render("news", {articles: recent_news[category].articles});
            return;
        }
    }
    
    newsapi.v2.topHeadlines({
        q: 'coronavirus',
        language: 'en',
        country: 'us',
        category: category
    }).then(
        response => {
            recent_news[category] = {
                articles: removeDuplicateArticles(response.articles),
                update_time: Date.now()
            }
            res.render("news", {articles: recent_news[category].articles.slice(0, 10)});
        }
    ).catch(
        response => {
            console.log("There was an error during the News API! ", response);
            res.render("news", {articles: []});
        }
    );
});

/* History Page - lists the first days */
app.get("/history", (req, res) => {
    res.render("spread_history");
});

/* Contact Page - lists ways you can reach us for feedback or feature requests */
app.get("/contact", (req, res) => {
    res.render("contact");
});

/* Simulate Curve Page - would let you input the population, healthcare system capacity,
 * and growth rate of the virus. We aren't sure if we should do it yet though. */
app.get("/simulate/curve", (req, res) => {
    res.render("simulate_curve");
});

/* Sources Page - lists the sources we use (Worldometers, BNO news, JHU, covid.iscii.es, etc.) */
app.get("/sources", (req, res) => {
    res.render("sources");
});

app.get("/test-gcloud", (req, res) => {
    res.send("Domain is directed to Google Cloud App Engine");
});

app.get("/data", (req, res) => {
    let query = "select * from datapoints where entry_date='2020-04-20'";
    if (req['region']) {
        query += " and group=" + sqlstring.escape(req['region']);
    }
    if (req['country']) {
        query += " and admin0=" + sqlstring.escape(req['country']);
    }
    if (req['province']) {
        query += " and admin1=" + sqlstring.escape(req['province']);
    }
    get_sql(query).then(
        data => {
            res.render("data_table", {table_rows: datatables.make_rows(data, "", "", "")});
        }
    ).catch(
        err => {
            res.send("We're sorry, there's been an error!");
        }
    );
});

const hostname = '0.0.0.0';
const port = process.env.PORT || 4040;

function get(params, field) {
    if (field in params) return params[field];
    else return null;
}

function get_sql(query, key = query) {
    return new Promise(function(resolve, reject) {
        // if this query is in the cache, and it was updated less than a minute ago, return the cached version
        if (sql_cache.hasOwnProperty(key) && (Date.now() - sql_cache[key].time) < sql_cache_age) {
            resolve(sql_cache[key].content);
        } else {
            corona_sql.sql.query(query,
                (err, result, fields) => {
                    if (err) throw err;

                    // updated the cache
                    sql_cache[key] = {"content": result, "time": Date.now()};
                    resolve(sql_cache[key].content);
                });
        }
    });
    
}

const sql_cache = {};
const sql_cache_age = 60000;

app.listen(port, () => console.log(`Server started at ${hostname}:${port}!`));