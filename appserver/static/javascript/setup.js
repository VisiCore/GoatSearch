var generation = 1;

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

    $("input[aria-label='Client Secret']").attr('type', 'password');

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

    var tenantConfTable = new TableView({
        id: "goatsearch_configured_tenants_table",
        managerid: "goatsearch_configured_tenants",
        drilldown: "none",
        el: $("#goatsearch_tenant_results"),
        pageSize: 100
    });

    // Create a basic custom row renderer
    var CellButtonRenderer = TableView.BaseCellRenderer.extend({
        canRender: function(rowData) {
            return true;
        },

        render: function($container, cell) {
            if ( cell.value && cell.field == "controls" ) {
                const params = cell.value.split(";");

                 if ( params[1] == "1" ) {
                    var btn_class = "edit-btn";
                    var disable_prop = ' disabled';
                } else {
                    var btn_class = "btn-primary"; 
                    var disable_prop = '';               
                }

                $container.html(`
                    <a class="btn btn-primary" aria-label="Search Button" href="#"><i class="icon-search-thin"></i></a>
                    <button class="btn btn-primary goatsearch-edit" data-target="${params[0]}">Edit</button>
                    <button class="btn btn-delete goatsearch-delete" data-target="${params[0]}">Delete</button>
                    <button class="btn ${btn_class} goatsearch-default" data-target="${params[0]}"${disable_prop}>Make Default</button>
                `);
            } else if ( cell.field == "default" ) {
                if ( cell.value && cell.value == "1" ) {
                    $container.html(`<div class="btn-primary default-tenant">✔</div>`);
                } else {
                    $container.text('');
                }
            } else {
                // Accounting for the stanza weirdness.
                $container.text(cell.value);
            }
        }
    });

    // Add the row renderer to the table
    tenantConfTable.addCellRenderer(new CellButtonRenderer());

    // Render the table
    tenantConfTable.render();

    $(document).on("click", ".goatsearch-edit", function(e) {
        e.preventDefault();

        $(".goatsearch-edit").addClass("btn-primary");
        $(".goatsearch-edit").removeClass("edit-btn");
        $(".goatsearch-edit").prop('disabled', false);

        $(this).removeClass("btn-primary");
        $(this).addClass("edit-btn");
        $(this).prop('disabled', true);

        globalSetToken('form.editCCID', $(this).attr('data-target'));
    });

    $(document).on("click", ".goatsearch-delete", function(e) {
        e.preventDefault();

        $(this).removeClass("btn-delete");
        $(this).addClass("edit-btn");
        $(this).prop('disabled', true);

        globalSetToken('deleteTenantKey', $(this).attr('data-target'));
    });

    $(document).on("click", "#add_edit_tenant", function(e) {
        e.preventDefault();

        const defaultChecked = $("div[id^=newCCDefault] button[role='checkbox']").attr('aria-checked');
        const editId = tokens.get('editCCID');

        var updateToken;

        if ( editId ) {
            updateToken = 'calculatedEditDefault';
        } else {
            updateToken = 'calculatedDefault';
        }

        if ( defaultChecked == "true" ) {
            globalSetToken(updateToken, "1");
            globalSetToken('clearSetDefaults', 'true');
        } else {
            globalSetToken(updateToken, "0");
        }
    });

    $(document).on("click", ".goatsearch-default", function(e) {
        e.preventDefault();

        $(this).removeClass("btn-primary");
        $(this).addClass("edit-btn");
        $(this).prop('disabled', true);

        globalSetToken('lastCreatedId', $(this).attr('data-target'));
    });

});
