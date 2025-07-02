require([
    "splunkjs/mvc",
    "splunkjs/mvc/searchmanager",
    "splunkjs/mvc/tableview",
    "splunkjs/mvc/simplexml/ready!"
], function(
    mvc,
    SearchManager,
    TableView
) {
    var tokens = mvc.Components.get("default");
    var stokens = mvc.Components.get("submitted");

    function globalSetToken(token, value ) {
        tokens.set(token, value);
        stokens.set(token, value);
    }

    function globalUnsetToken(token) {
        tokens.unset(token);
        stokens.unset(token);
    }

    function updateSPLSearch() {
        const csearch = $("#csearch_query").val();

        if ( !csearch ) {
            globalUnsetToken('queryString');
        } else {
            const regex = /"/ig
            const csearchSafe = csearch.replace(regex, "'");

            globalSetToken('queryString', ` query="${csearchSafe}"`)
        }
    }

    $(document).on("input", "#csearch_query", function(e) {
        updateSPLSearch();
    });

    $(document).on("click", "#csearch_open", function(e) {
        const goatsearch = $("#csearch_string").text();
        const earliest = tokens.get('tokenCSearchTime.earliest');
        const latest  = tokens.get('tokenCSearchTime.latest');

        window.open(`/app/GoatSearch/search?earliest=${earliest}&latest=${latest}&q=${goatsearch}`, '_blank').focus();
    });

    updateSPLSearch();
});

