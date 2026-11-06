
import os
import csv
import io
from datetime import datetime

from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, Response, send_file
)

import mysql.connector
from mysql.connector import Error


app = Flask(__name__)
app.secret_key = os.getenv(
    "SECRET_KEY",
    "bincom-local-assessment-secret"
)


# DATABASE CONNECTION
# Local MariaDB account has no password.

def get_connection():
    return mysql.connector.connect(
        host="127.0.0.1",
        port=3306,
        user="bincom_app",
        password="",
        database="bincom_test"
    )


# DATABASE QUERY HELPER

def query_all(sql, params=()):
    conn = get_connection()
    cur = None

    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params)
        return cur.fetchall()

    finally:
        if cur is not None:
            cur.close()
        conn.close()


# HOMEPAGE

@app.route("/")
def home():
    try:
        stats = query_all("""
            SELECT
                (
                    SELECT COUNT(*)
                    FROM lga
                    WHERE state_id = 25
                ) AS lgas,

                (
                    SELECT COUNT(*)
                    FROM polling_unit
                    WHERE lga_id IN (
                        SELECT lga_id
                        FROM lga
                        WHERE state_id = 25
                    )
                ) AS polling_units,

                (
                    SELECT COUNT(*)
                    FROM announced_pu_results
                ) AS result_rows
        """)[0]

    except Error as exc:
        stats = None
        flash(f"Database connection problem: {exc}", "error")

    return render_template("index.html", stats=stats)


# REQUIREMENT 1:
# DISPLAY RESULTS FOR AN INDIVIDUAL POLLING UNIT

@app.route("/polling-unit", methods=["GET", "POST"])
def polling_unit_results():

    units = query_all("""
        SELECT DISTINCT
            pu.uniqueid,
            pu.polling_unit_name,
            pu.polling_unit_number,
            w.ward_name,
            l.lga_name

        FROM polling_unit pu

        LEFT JOIN ward w
            ON w.ward_id = pu.ward_id
            AND w.lga_id = pu.lga_id

        LEFT JOIN lga l
            ON l.lga_id = pu.lga_id

        WHERE l.state_id = 25

        ORDER BY
            l.lga_name,
            w.ward_name,
            pu.uniqueid
    """)

    selected_id = request.values.get(
        "polling_unit_uniqueid",
        type=int
    )

    results = []
    selected_unit = None

    if selected_id:

        rows = query_all("""
            SELECT
                pu.uniqueid,
                pu.polling_unit_name,
                pu.polling_unit_number,
                w.ward_name,
                l.lga_name

            FROM polling_unit pu

            LEFT JOIN ward w
                ON w.ward_id = pu.ward_id
            AND w.lga_id = pu.lga_id

            LEFT JOIN lga l
                ON l.lga_id = pu.lga_id

            WHERE pu.uniqueid = %s
            AND l.state_id = 25
        """, (selected_id,))

        if rows:
            selected_unit = rows[0]

            results = query_all("""
                SELECT
                    party_abbreviation,
                    SUM(party_score) AS party_score

                FROM announced_pu_results

                WHERE CAST(TRIM(polling_unit_uniqueid) AS UNSIGNED) = %s

                GROUP BY party_abbreviation

                ORDER BY party_abbreviation
            """, (str(selected_id),))

    return render_template(
        "polling_unit.html",
        units=units,
        selected_id=selected_id,
        selected_unit=selected_unit,
        results=results
    )


# REQUIREMENT 2:
# AGGREGATE POLLING UNIT RESULTS FOR A SELECTED LGA

@app.route("/lga-results", methods=["GET", "POST"])
def lga_results():

    lgas = query_all("""
        SELECT lga_id AS uniqueid, lga_name
        FROM lga
        WHERE state_id = 25
        ORDER BY lga_name
    """)

    selected_lga = request.values.get("lga_id", type=int)

    results = []
    selected_name = None

    if selected_lga:

        matches = [
            item for item in lgas
            if item["uniqueid"] == selected_lga
        ]

        if matches:

            selected_name = matches[0]["lga_name"]

            # Aggregate from announced polling-unit results.
            # Do not use announced_lga_results.

            results = query_all("""
                SELECT
                    apr.party_abbreviation,
                    SUM(apr.party_score) AS total_score

                FROM announced_pu_results apr

                INNER JOIN polling_unit pu
                    ON CAST(TRIM(apr.polling_unit_uniqueid) AS UNSIGNED) = pu.uniqueid

                WHERE pu.lga_id = %s
                  AND EXISTS (
                      SELECT 1 FROM lga selected_lga
                      WHERE selected_lga.lga_id = pu.lga_id
                        AND selected_lga.state_id = 25
                  )

                GROUP BY apr.party_abbreviation

                ORDER BY
                    total_score DESC,
                    apr.party_abbreviation
            """, (selected_lga,))

    return render_template(
        "lga_results.html",
        lgas=lgas,
        selected_lga=selected_lga,
        selected_name=selected_name,
        results=results
    )


# REQUIREMENT 3:
# ENTER RESULTS FOR A NEW POLLING UNIT

@app.route("/new-polling-unit", methods=["GET", "POST"])
def new_polling_unit():

    lgas = query_all("""
        SELECT lga_id AS uniqueid, lga_name
        FROM lga
        WHERE state_id = 25
        ORDER BY lga_name
    """)

    parties = query_all("""
        SELECT partyid, partyname
        FROM party
        ORDER BY partyid
    """)

    wards = []

    selected_lga = request.values.get(
        "lga_id",
        type=int
    )

    if selected_lga:

        wards = query_all("""
            SELECT ward_id AS uniqueid, ward_name
            FROM ward
            WHERE lga_id = %s
            ORDER BY ward_name
        """, (selected_lga,))

    if request.method == "POST":

        conn = None
        cur = None

        try:
            polling_unit_id = int(
                request.form["polling_unit_id"]
            )

            ward_id = int(request.form["ward_id"])
            lga_id = int(request.form["lga_id"])

            unit_number = request.form.get(
                "polling_unit_number", ""
            ).strip()

            unit_name = request.form.get(
                "polling_unit_name", ""
            ).strip()

            if polling_unit_id <= 0:
                raise ValueError(
                    "Polling unit ID must be a positive number."
                )

            if not unit_name:
                raise ValueError(
                    "Polling unit name is required."
                )

            valid_lga = query_all("""
                SELECT lga_id
                FROM lga
                WHERE lga_id = %s
                AND state_id = 25
            """, (lga_id,))

            if not valid_lga:
                raise ValueError(
                    "Please select a valid Delta State LGA."
                )

            valid_ward = query_all("""
                SELECT ward_id
                FROM ward
                WHERE ward_id = %s
                AND lga_id = %s
            """, (ward_id, lga_id))

            if not valid_ward:
                raise ValueError(
                    "The selected ward does not belong to the selected LGA."
                )

            scores = []

            for party in parties:

                party_id = party["partyid"]

                raw = request.form.get(
                    "score_" + party_id,
                    "0"
                ).strip()

                score = int(raw)

                if score < 0:
                    raise ValueError(
                        "Party scores cannot be negative."
                    )

                scores.append((party_id, score))

            duplicate = query_all("""
                SELECT uniqueid
                FROM polling_unit
                WHERE polling_unit_id = %s
                  AND lga_id = %s
                  AND ward_id = %s
            """, (polling_unit_id, lga_id, ward_id))
            if duplicate:
                raise ValueError("This polling unit ID already exists in the selected ward and LGA.")

            conn = get_connection()
            conn.start_transaction()

            cur = conn.cursor()

            now = datetime.now()
            user_ip = request.remote_addr or "127.0.0.1"

            cur.execute("""
                INSERT INTO polling_unit (
                    polling_unit_id,
                    ward_id,
                    lga_id,
                    polling_unit_number,
                    polling_unit_name,
                    entered_by_user,
                    date_entered,
                    user_ip_address
                )

                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                polling_unit_id,
                ward_id,
                lga_id,
                unit_number,
                unit_name,
                "Bincom Assessment",
                now,
                user_ip
            ))

            new_uniqueid = cur.lastrowid

            for abbreviation, score in scores:

                cur.execute("""
                    INSERT INTO announced_pu_results (
                        polling_unit_uniqueid,
                        party_abbreviation,
                        party_score,
                        entered_by_user,
                        date_entered,
                        user_ip_address
                    )

                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    str(new_uniqueid),
                    abbreviation,
                    score,
                    "Bincom Assessment",
                    now,
                    user_ip
                ))

            conn.commit()

            flash(
                f"Polling unit and {len(scores)} party results saved successfully. New unique ID: {new_uniqueid}",
                "success"
            )

            return redirect(
                url_for("new_polling_unit")
            )

        except (ValueError, KeyError) as exc:

            if conn is not None:
                conn.rollback()

            flash(str(exc), "error")

        except Error as exc:

            if conn is not None:
                conn.rollback()

            flash(
                f"Database error. No records were saved: {exc}",
                "error"
            )

        finally:

            if cur is not None:
                cur.close()

            if conn is not None:
                conn.close()

    return render_template(
        "new_polling_unit.html",
        lgas=lgas,
        wards=wards,
        parties=parties,
        selected_lga=selected_lga
    )


# CSV EXPORT: LGA RESULTS

@app.route("/export/lga/<int:lga_id>.csv")
def export_lga_csv(lga_id):

    lgas = query_all("""
        SELECT lga_id AS uniqueid, lga_name
        FROM lga
        WHERE lga_id = %s
        AND state_id = 25
    """, (lga_id,))

    if not lgas:
        flash("Selected LGA was not found.", "error")
        return redirect(url_for("lga_results"))

    rows = query_all("""
        SELECT
            apr.party_abbreviation,
            SUM(apr.party_score) AS total_score

        FROM announced_pu_results apr

        INNER JOIN polling_unit pu
            ON CAST(TRIM(apr.polling_unit_uniqueid) AS UNSIGNED) = pu.uniqueid

        WHERE pu.lga_id = %s

        GROUP BY apr.party_abbreviation

        ORDER BY total_score DESC
    """, (lga_id,))

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["LGA", lgas[0]["lga_name"]])
    writer.writerow(["Party", "Total votes"])

    for row in rows:
        writer.writerow([
            row["party_abbreviation"],
            row["total_score"]
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition":
            f"attachment; filename=lga_{lga_id}_results.csv"
        }
    )


# CSV EXPORT: POLLING UNIT RESULTS

@app.route("/export/polling-unit/<int:unit_id>.csv")
def export_polling_unit_csv(unit_id):

    units = query_all("""
        SELECT
            pu.uniqueid,
            pu.polling_unit_name,
            l.lga_name

        FROM polling_unit pu

        JOIN lga l
            ON l.lga_id = pu.lga_id

        WHERE pu.uniqueid = %s
        AND l.state_id = 25
    """, (unit_id,))

    if not units:
        flash(
            "Selected polling unit was not found.",
            "error"
        )
        return redirect(url_for("polling_unit_results"))

    rows = query_all("""
        SELECT
            party_abbreviation,
            SUM(party_score) AS party_score

        FROM announced_pu_results

        WHERE polling_unit_uniqueid = %s

        GROUP BY party_abbreviation

        ORDER BY party_abbreviation
    """, (str(unit_id),))

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Polling unit",
        units[0]["polling_unit_name"] or units[0]["uniqueid"]
    ])

    writer.writerow(["LGA", units[0]["lga_name"]])
    writer.writerow(["Party", "Votes"])

    for row in rows:
        writer.writerow([
            row["party_abbreviation"],
            row["party_score"]
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition":
            f"attachment; filename=polling_unit_{unit_id}_results.csv"
        }
    )


# COMMON EXPORT DATA FUNCTION

def build_export_rows(report_type, record_id):

    if report_type == "lga":

        lgas = query_all("""
            SELECT lga_id AS uniqueid, lga_name
            FROM lga
            WHERE lga_id = %s
            AND state_id = 25
        """, (record_id,))

        if not lgas:
            raise ValueError("LGA not found.")

        rows = query_all("""
            SELECT
                apr.party_abbreviation AS party,
                SUM(apr.party_score) AS votes

            FROM announced_pu_results apr

            INNER JOIN polling_unit pu
                ON CAST(
                    apr.polling_unit_uniqueid AS UNSIGNED
                ) = pu.uniqueid

            WHERE pu.lga_id = %s

            GROUP BY apr.party_abbreviation

            ORDER BY votes DESC
        """, (record_id,))

        title = "LGA Results - " + lgas[0]["lga_name"]

    else:

        units = query_all("""
            SELECT
                pu.uniqueid,
                pu.polling_unit_name

            FROM polling_unit pu

            JOIN lga l
                ON l.lga_id = pu.lga_id

            WHERE pu.uniqueid = %s
            AND l.state_id = 25
        """, (record_id,))

        if not units:
            raise ValueError("Polling unit not found.")

        rows = query_all("""
            SELECT
                party_abbreviation AS party,
                SUM(party_score) AS votes

            FROM announced_pu_results

            WHERE polling_unit_uniqueid = %s

            GROUP BY party_abbreviation

            ORDER BY party_abbreviation
        """, (str(record_id),))

        title = (
            "Polling Unit Results - "
            + str(units[0]["polling_unit_name"] or record_id)
        )

    return title, rows


# EXCEL EXPORT

@app.route("/export/<report_type>/<int:record_id>.xlsx")
def export_xlsx(report_type, record_id):

    if report_type not in ("lga", "polling-unit"):
        return "Unsupported report", 404

    try:

        from openpyxl import Workbook

        title, rows = build_export_rows(
            "lga" if report_type == "lga" else "polling",
            record_id
        )

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Election Results"

        sheet.append([title])
        sheet.append(["Political Party", "Votes"])

        for row in rows:
            sheet.append([
                row["party"],
                row["votes"]
            ])

        sheet.column_dimensions["A"].width = 28
        sheet.column_dimensions["B"].width = 18

        output = io.BytesIO()
        workbook.save(output)
        output.seek(0)

        return send_file(
            output,
            as_attachment=True,
            download_name=f"{report_type}_{record_id}_results.xlsx",
            mimetype=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            )
        )

    except ImportError:
        return "Install openpyxl to export Excel files.", 500

    except ValueError as exc:
        return str(exc), 404


# PDF EXPORT

@app.route("/export/<report_type>/<int:record_id>.pdf")
def export_pdf(report_type, record_id):

    if report_type not in ("lga", "polling-unit"):
        return "Unsupported report", 404

    try:

        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import (
            SimpleDocTemplate,
            Paragraph,
            Spacer,
            Table,
            TableStyle
        )
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet

        title, rows = build_export_rows(
            "lga" if report_type == "lga" else "polling",
            record_id
        )

        output = io.BytesIO()

        doc = SimpleDocTemplate(
            output,
            pagesize=A4
        )

        styles = getSampleStyleSheet()

        story = [
            Paragraph(title, styles["Title"]),
            Spacer(1, 18)
        ]

        data = [
            ["Political Party", "Votes"]
        ] + [
            [row["party"], f'{row["votes"]:,}']
            for row in rows
        ]

        table = Table(
            data,
            colWidths=[260, 150]
        )

        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0),
             colors.HexColor("#008751")),

            ("TEXTCOLOR", (0, 0), (-1, 0),
             colors.white),

            ("GRID", (0, 0), (-1, -1),
             0.5, colors.HexColor("#dce7df")),

            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.white, colors.HexColor("#f2f7f4")]),

            ("ALIGN", (1, 1), (1, -1), "RIGHT"),

            ("PADDING", (0, 0), (-1, -1), 9)
        ]))

        story.append(table)
        story.append(Spacer(1, 18))

        story.append(Paragraph(
            "Source: announced polling-unit results in the supplied assessment database.",
            styles["BodyText"]
        ))

        doc.build(story)
        output.seek(0)

        return send_file(
            output,
            as_attachment=True,
            download_name=f"{report_type}_{record_id}_results.pdf",
            mimetype="application/pdf"
        )

    except ImportError:
        return "Install reportlab to export PDF files.", 500

    except ValueError as exc:
        return str(exc), 404


# ERROR HANDLER

@app.errorhandler(500)
def server_error(error):

    return render_template(
        "error.html",
        message="An unexpected server error occurred."
    ), 500


# START APPLICATION

if __name__ == "__main__":

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=os.getenv("FLASK_DEBUG", "0") == "1"
    )
