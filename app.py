from datetime import datetime
import pandas as pd
import sqlite3
import streamlit as st

DB_NAME = "finanzas.db"


def inicializar_bd():
  conn = sqlite3.connect(DB_NAME)
  cursor = conn.cursor()

  cursor.execute("""
        CREATE TABLE IF NOT EXISTS cuentas (
            id_cuenta INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_cuenta TEXT NOT NULL,
            tipo_cuenta TEXT NOT NULL,
            saldo_inicial REAL DEFAULT 0.0,
            cotizacion REAL DEFAULT 1.0
        )
    """)

  try:
    cursor.execute("ALTER TABLE cuentas ADD COLUMN cotizacion REAL DEFAULT 1.0")
  except sqlite3.OperationalError:
    pass

  cursor.execute("""
        CREATE TABLE IF NOT EXISTS categorias (
            id_categoria INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            tipo TEXT NOT NULL
        )
    """)

  cursor.execute("""
        CREATE TABLE IF NOT EXISTS movimientos (
            id_movimiento INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,
            tipo_movimiento TEXT NOT NULL,
            id_cuenta_origen INTEGER,
            id_cuenta_destino INTEGER,
            id_categoria INTEGER,
            monto REAL NOT NULL,
            estado TEXT DEFAULT 'Pagado',
            descripcion TEXT
        )
    """)

  cursor.execute("SELECT COUNT(*) FROM cuentas")
  if cursor.fetchone()[0] == 0:
    cursor.executemany(
        "INSERT INTO cuentas (nombre_cuenta, tipo_cuenta, saldo_inicial,"
        " cotizacion) VALUES (?, ?, ?, ?)",
        [
            ("Efectivo", "Efectivo", 0.0, 1.0),
            ("Banco Galicia", "Banco", 0.0, 1.0),
            ("Mercado Pago", "Billetera Virtual", 0.0, 1.0),
        ],
    )

  cursor.execute("SELECT COUNT(*) FROM categorias")
  if cursor.fetchone()[0] == 0:
    cursor.executemany(
        "INSERT INTO categorias (nombre, tipo) VALUES (?, ?)",
        [
            ("Sueldo", "Ingreso"),
            ("Alquiler Cobrado", "Ingreso"),
            ("Honorarios", "Ingreso"),
            ("Servicios (Luz/Internet)", "Egreso"),
            ("Alimentación", "Egreso"),
            ("Gastos Extraordinarios", "Egreso"),
            ("Ajuste de Saldo / Varios", "Ambos"),
        ],
    )

  conn.commit()
  conn.close()


inicializar_bd()

st.set_page_config(
    page_title="Control de Fondos", page_icon="💰", layout="wide"
)

st.title("💰 Sistema de Control y Flujo de Fondos")

menu = st.sidebar.selectbox(
    "Menú Principal",
    [
        "Resumen de Cuentas",
        "Registrar Movimiento",
        "Historial de Movimientos",
        "Administrar Cuentas y Categorías",
    ],
)


def consultar_sql(query, params=()):
  conn = sqlite3.connect(DB_NAME)
  df = pd.read_sql_query(query, conn, params=params)
  conn.close()
  return df


# --- SECCIÓN 1: RESUMEN DE CUENTAS Y EXTRACTO CON EDICIÓN DIRECTA ---
if menu == "Resumen de Cuentas":
  st.header("📊 Cuentas y Activos (Valores en Pesos)")

  query_saldos = """
        SELECT 
            c.id_cuenta,
            c.nombre_cuenta,
            c.tipo_cuenta,
            c.saldo_inicial,
            c.cotizacion,
            COALESCE(SUM(CASE WHEN m.id_cuenta_destino = c.id_cuenta AND m.estado = 'Pagado' THEN m.monto ELSE 0 END), 0) -
            COALESCE(SUM(CASE WHEN m.id_cuenta_origen = c.id_cuenta AND m.estado = 'Pagado' THEN m.monto ELSE 0 END), 0) as movimientos_netos,
            ((c.saldo_inicial + 
             COALESCE(SUM(CASE WHEN m.id_cuenta_destino = c.id_cuenta AND m.estado = 'Pagado' THEN m.monto ELSE 0 END), 0) -
             COALESCE(SUM(CASE WHEN m.id_cuenta_origen = c.id_cuenta AND m.estado = 'Pagado' THEN m.monto ELSE 0 END), 0)
            ) * c.cotizacion) as saldo_actual
        FROM cuentas c
        LEFT JOIN movimientos m ON c.id_cuenta = m.id_cuenta_origen OR c.id_cuenta = m.id_cuenta_destino
        GROUP BY c.id_cuenta
        ORDER BY c.tipo_cuenta ASC, c.nombre_cuenta ASC
    """
  df_cuentas = consultar_sql(query_saldos)

  if not df_cuentas.empty:
    saldo_total = df_cuentas["saldo_actual"].sum()
    st.metric(
        "💰 Total Consolidado Global (en Pesos)", f"${saldo_total:,.2f}"
    )
    st.markdown("---")

    if "cuenta_seleccionada_ext" not in st.session_state:
      st.session_state.cuenta_seleccionada_ext = None

    if st.session_state.cuenta_seleccionada_ext is None:
      st.subheader("📋 Listado de Cuentas")

      h_cols = st.columns([2, 2, 2, 2, 1])
      h_cols[0].markdown("**Nombre de Cuenta**")
      h_cols[1].markdown("**Tipo**")
      h_cols[2].markdown("**Saldo Inicial**")
      h_cols[3].markdown("**Saldo Actual ($)**")
      h_cols[4].markdown("**Acción**")
      st.markdown("---")

      for idx, row in df_cuentas.iterrows():
        cols = st.columns([2, 2, 2, 2, 1])
        cols[0].write(row["nombre_cuenta"])
        cols[1].write(row["tipo_cuenta"])
        cols[2].write(f"${row['saldo_inicial']:,.2f}")
        cols[3].write(f"**${row['saldo_actual']:,.2f}**")
        if cols[4].button("🔍 Ver", key=f"btn_cta_{row['id_cuenta']}"):
          st.session_state.cuenta_seleccionada_ext = row["id_cuenta"]
          st.rerun()

    else:
      id_cta_activa = st.session_state.cuenta_seleccionada_ext
      nombre_cta_act = df_cuentas[df_cuentas["id_cuenta"] == id_cta_activa][
          "nombre_cuenta"
      ].values[0]

      if st.button("⬅️ Volver al Resumen de Cuentas"):
        st.session_state.cuenta_seleccionada_ext = None
        st.rerun()

      st.markdown("---")
      st.subheader(f"🔍 Extracto de Movimientos: {nombre_cta_act}")

      conn_tmp = sqlite3.connect(DB_NAME)
      saldo_inicial_cta = pd.read_sql_query(
          "SELECT saldo_inicial FROM cuentas WHERE id_cuenta = ?",
          conn_tmp,
          params=(id_cta_activa,),
      ).iloc[0]["saldo_inicial"]
      conn_tmp.close()

      query_extracto_asc = """
                SELECT m.id_movimiento, m.fecha, m.tipo_movimiento, 
                m.id_cuenta_origen, m.id_cuenta_destino,
                COALESCE(c1.nombre_cuenta, '-') as origen, 
                COALESCE(c2.nombre_cuenta, '-') as destino, 
                COALESCE(cat.nombre, 'Transferencia') as categoria, 
                m.monto, m.estado, m.descripcion
                FROM movimientos m
                LEFT JOIN cuentas c1 ON m.id_cuenta_origen = c1.id_cuenta
                LEFT JOIN cuentas c2 ON m.id_cuenta_destino = c2.id_cuenta
                LEFT JOIN categorias cat ON m.id_categoria = cat.id_categoria
                WHERE (m.id_cuenta_origen = ? OR m.id_cuenta_destino = ?)
                ORDER BY m.fecha ASC, m.id_movimiento ASC
            """
      df_ext = consultar_sql(
          query_extracto_asc, params=(id_cta_activa, id_cta_activa)
      )

      if not df_ext.empty:
        saldo_acumulado = saldo_inicial_cta
        saldos = []
        for idx, row in df_ext.iterrows():
          if row["estado"] == "Pagado":
            if row["id_cuenta_destino"] == id_cta_activa:
              saldo_acumulado += row["monto"]
            if row["id_cuenta_origen"] == id_cta_activa:
              saldo_acumulado -= row["monto"]
          saldos.append(saldo_acumulado)

        df_ext["saldo"] = saldos
        df_ext_sorted = df_ext.sort_values(
            by=["fecha", "id_movimiento"], ascending=[False, False]
        ).reset_index(drop=True)

        df_mostrar = df_ext_sorted[[
            "id_movimiento",
            "fecha",
            "tipo_movimiento",
            "origen",
            "destino",
            "categoria",
            "monto",
            "saldo",
            "estado",
            "descripcion",
        ]]

        st.markdown(f"Saldo Inicial de la cuenta: **${saldo_inicial_cta:,.2f}**")
        st.dataframe(df_mostrar, use_container_width=True)

        st.markdown("---")
        st.subheader("✏️ Modificar o Eliminar un Movimiento de este Extracto")

        mov_ids = df_ext_sorted["id_movimiento"].tolist()
        mov_seleccionado = st.selectbox(
            "Seleccioná el ID de Movimiento a modificar/eliminar",
            options=mov_ids,
            format_func=lambda x: (
                f"ID {x} - "
                f"{df_ext_sorted[df_ext_sorted['id_movimiento'] == x]['fecha'].values[0]}"
                f" - "
                f"{df_ext_sorted[df_ext_sorted['id_movimiento'] == x]['tipo_movimiento'].values[0]}"
                f" - $"
                f"{df_ext_sorted[df_ext_sorted['id_movimiento'] == x]['monto'].values[0]}"
                f" ("
                f"{df_ext_sorted[df_ext_sorted['id_movimiento'] == x]['descripcion'].values[0]})"
            ),
            key=f"sel_mov_ext_{id_cta_activa}",
        )

        if mov_seleccionado:
          conn = sqlite3.connect(DB_NAME)
          mov_data = pd.read_sql_query(
              f"SELECT * FROM movimientos WHERE id_movimiento = {mov_seleccionado}",
              conn,
          ).iloc[0]
          cuentas_df = pd.read_sql_query(
              "SELECT id_cuenta, nombre_cuenta FROM cuentas ORDER BY tipo_cuenta"
              " ASC, nombre_cuenta ASC",
              conn,
          )
          categorias_df = pd.read_sql_query(
              "SELECT id_categoria, nombre, tipo FROM categorias ORDER BY"
              " nombre ASC",
              conn,
          )
          conn.close()

          col_edit, col_del = st.columns([3, 1])

          with col_edit:
            tipos_movs_opc = ["Ingreso", "Egreso", "Transferencia"]
            idx_tipo_def = (
                tipos_movs_opc.index(mov_data["tipo_movimiento"])
                if mov_data["tipo_movimiento"] in tipos_movs_opc
                else 0
            )
            e_tipo_mov = st.selectbox(
                "Tipo de Movimiento",
                tipos_movs_opc,
                index=idx_tipo_def,
                key=f"ext_edit_tipo_{mov_seleccionado}",
            )

            with st.form(f"form_edit_mov_ext_{mov_seleccionado}"):
              e_fecha = st.date_input(
                  "Fecha",
                  value=datetime.strptime(
                      mov_data["fecha"], "%Y-%m-%d"
                  ).date(),
              )

              e_cuenta_origen = None
              e_cuenta_destino = None
              e_id_cat = None

              if e_tipo_mov in ["Egreso", "Transferencia"]:
                orig_idx = 0
                if pd.notna(mov_data["id_cuenta_origen"]):
                  matches = cuentas_df[
                      cuentas_df["id_cuenta"] == mov_data["id_cuenta_origen"]
                  ].index
                  if len(matches) > 0:
                    orig_idx = list(cuentas_df["id_cuenta"]).index(
                        mov_data["id_cuenta_origen"]
                    )
                e_cuenta_origen = st.selectbox(
                    "Cuenta de Origen",
                    options=cuentas_df["id_cuenta"].tolist(),
                    index=orig_idx,
                    format_func=lambda x: cuentas_df[
                        cuentas_df["id_cuenta"] == x
                    ]["nombre_cuenta"].values[0],
                )

              if e_tipo_mov in ["Ingreso", "Transferencia"]:
                dest_idx = 0
                if pd.notna(mov_data["id_cuenta_destino"]):
                  matches = cuentas_df[
                      cuentas_df["id_cuenta"] == mov_data["id_cuenta_destino"]
                  ].index
                  if len(matches) > 0:
                    dest_idx = list(cuentas_df["id_cuenta"]).index(
                        mov_data["id_cuenta_destino"]
                    )
                e_cuenta_destino = st.selectbox(
                    "Cuenta de Destino",
                    options=cuentas_df["id_cuenta"].tolist(),
                    index=dest_idx,
                    format_func=lambda x: cuentas_df[
                        cuentas_df["id_cuenta"] == x
                    ]["nombre_cuenta"].values[0],
                )

              if e_tipo_mov != "Transferencia":
                cat_filtradas = categorias_df[
                    (categorias_df["tipo"] == e_tipo_mov)
                    | (categorias_df["tipo"] == "Ambos")
                ]
                cat_idx = 0
                if (
                    pd.notna(mov_data["id_categoria"])
                    and not cat_filtradas.empty
                ):
                  if (
                      mov_data["id_categoria"]
                      in cat_filtradas["id_categoria"].tolist()
                  ):
                    cat_idx = list(cat_filtradas["id_categoria"]).index(
                        mov_data["id_categoria"]
                    )
                if not cat_filtradas.empty:
                  e_id_cat = st.selectbox(
                      "Categoría",
                      options=cat_filtradas["id_categoria"].tolist(),
                      index=cat_idx,
                      format_func=lambda x: cat_filtradas[
                          cat_filtradas["id_categoria"] == x
                      ]["nombre"].values[0],
                  )

              e_monto = st.number_input(
                  "Monto ($)", value=float(mov_data["monto"]), step=100.0
              )
              e_estado = st.selectbox(
                  "Estado",
                  ["Pagado", "Pendiente"],
                  index=0 if mov_data["estado"] == "Pagado" else 1,
              )
              e_desc = st.text_input(
                  "Descripción", value=str(mov_data["descripcion"] or "")
              )

              btn_update = st.form_submit_button("Guardar Cambios")

              if btn_update:
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()
                cursor.execute(
                    """
                                UPDATE movimientos 
                                SET tipo_movimiento = ?, fecha = ?, id_cuenta_origen = ?, id_cuenta_destino = ?, id_categoria = ?, monto = ?, estado = ?, descripcion = ?
                                WHERE id_movimiento = ?
                            """,
                    (
                        e_tipo_mov,
                        str(e_fecha),
                        e_cuenta_origen,
                        e_cuenta_destino,
                        e_id_cat,
                        e_monto,
                        e_estado,
                        e_desc,
                        mov_seleccionado,
                    ),
                )
                conn.commit()
                conn.close()
                st.success("¡Movimiento actualizado con éxito!")
                st.rerun()

          with col_del:
            st.write("🗑️ **Eliminar**")
            if st.button(
                "Eliminar este Movimiento",
                key=f"btn_del_ext_{mov_seleccionado}",
            ):
              conn = sqlite3.connect(DB_NAME)
              cursor = conn.cursor()
              cursor.execute(
                  "DELETE FROM movimientos WHERE id_movimiento = ?",
                  (mov_seleccionado,),
              )
              conn.commit()
              conn.close()
              st.warning("Movimiento eliminado.")
              st.rerun()

      else:
        st.info("No hay movimientos registrados para esta cuenta.")

  else:
    st.info("No hay cuentas cargadas.")

# --- SECCIÓN 2: REGISTRAR MOVIMIENTO ---
elif menu == "Registrar Movimiento":
  st.header("📝 Nuevo Movimiento de Fondos")

  conn = sqlite3.connect(DB_NAME)
  cuentas_df = pd.read_sql_query(
      "SELECT id_cuenta, nombre_cuenta FROM cuentas ORDER BY tipo_cuenta ASC,"
      " nombre_cuenta ASC",
      conn,
  )
  categorias_df = pd.read_sql_query(
      "SELECT id_categoria, nombre, tipo FROM categorias ORDER BY nombre ASC",
      conn,
  )
  conn.close()

  if cuentas_df.empty:
    st.warning(
        "Primero debés crear al menos una cuenta en 'Administrar Cuentas y"
        " Categorías'."
    )
  else:
    tipo_mov = st.selectbox(
        "Tipo de Movimiento", ["Ingreso", "Egreso", "Transferencia"]
    )

    with st.form("form_movimiento"):
      fecha = st.date_input("Fecha", value=datetime.today())

      cuenta_origen = None
      cuenta_destino = None
      id_cat = None

      if tipo_mov == "Egreso":
        st.write("📤 **Configuración de Egreso (Gasto / Pago)**")
        cuenta_origen = st.selectbox(
            "Cuenta de Origen",
            options=cuentas_df["id_cuenta"].tolist(),
            format_func=lambda x: cuentas_df[cuentas_df["id_cuenta"] == x][
                "nombre_cuenta"
            ].values[0],
        )

        cat_filtradas = categorias_df[
            (categorias_df["tipo"] == "Egreso")
            | (categorias_df["tipo"] == "Ambos")
        ]
        if not cat_filtradas.empty:
          id_cat = st.selectbox(
              "Categoría de Gasto",
              options=cat_filtradas["id_categoria"].tolist(),
              format_func=lambda x: cat_filtradas[
                  cat_filtradas["id_categoria"] == x
              ]["nombre"].values[0],
          )

      elif tipo_mov == "Ingreso":
        st.write("📥 **Configuración de Ingreso (Cobro / Sueldos)**")
        cuenta_destino = st.selectbox(
            "Cuenta de Destino",
            options=cuentas_df["id_cuenta"].tolist(),
            format_func=lambda x: cuentas_df[cuentas_df["id_cuenta"] == x][
                "nombre_cuenta"
            ].values[0],
        )

        cat_filtradas = categorias_df[
            (categorias_df["tipo"] == "Ingreso")
            | (categorias_df["tipo"] == "Ambos")
        ]
        if not cat_filtradas.empty:
          id_cat = st.selectbox(
              "Categoría de Ingreso",
              options=cat_filtradas["id_categoria"].tolist(),
              format_func=lambda x: cat_filtradas[
                  cat_filtradas["id_categoria"] == x
              ]["nombre"].values[0],
          )

      elif tipo_mov == "Transferencia":
        st.write("🔄 **Configuración de Transferencia**")
        cuenta_origen = st.selectbox(
            "Cuenta de Origen",
            options=cuentas_df["id_cuenta"].tolist(),
            format_func=lambda x: cuentas_df[cuentas_df["id_cuenta"] == x][
                "nombre_cuenta"
            ].values[0],
        )
        cuenta_destino = st.selectbox(
            "Cuenta de Destino",
            options=cuentas_df["id_cuenta"].tolist(),
            format_func=lambda x: cuentas_df[cuentas_df["id_cuenta"] == x][
                "nombre_cuenta"
            ].values[0],
        )

      st.markdown("---")
      monto = st.number_input("Monto", min_value=0.0, step=100.0)
      estado = st.selectbox("Estado", ["Pagado", "Pendiente"])
      descripcion = st.text_input("Descripción / Concepto")

      submitted = st.form_submit_button("Guardar Transacción")

      if submitted:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            """
                    INSERT INTO movimientos (fecha, tipo_movimiento, id_cuenta_origen, id_cuenta_destino, id_categoria, monto, estado, descripcion)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
            (
                str(fecha),
                tipo_mov,
                cuenta_origen,
                cuenta_destino,
                id_cat,
                monto,
                estado,
                descripcion,
            ),
        )
        conn.commit()
        conn.close()
        st.success("¡Movimiento guardado con éxito!")

# --- SECCIÓN 3: HISTORIAL Y EDICIÓN DE MOVIMIENTOS ---
elif menu == "Historial de Movimientos":
  st.header("📋 Historial General de Movimientos")
  query = """
        SELECT m.id_movimiento, m.fecha, m.tipo_movimiento, 
        COALESCE(c1.nombre_cuenta, '-') as origen, 
        COALESCE(c2.nombre_cuenta, '-') as destino, 
        COALESCE(cat.nombre, 'Transferencia') as categoria, 
        m.monto, m.estado, m.descripcion
        FROM movimientos m
        LEFT JOIN cuentas c1 ON m.id_cuenta_origen = c1.id_cuenta
        LEFT JOIN cuentas c2 ON m.id_cuenta_destino = c2.id_cuenta
        LEFT JOIN categorias cat ON m.id_categoria = cat.id_categoria
        ORDER BY m.fecha DESC, m.id_movimiento DESC
    """
  df_mov = consultar_sql(query)

  if not df_mov.empty:
    st.dataframe(df_mov, use_container_width=True)

    st.markdown("---")
    st.subheader("✏️ Modificar o Eliminar un Movimiento")

    mov_ids = df_mov["id_movimiento"].tolist()
    mov_seleccionado = st.selectbox(
        "Seleccioná el ID de Movimiento a modificar/eliminar",
        options=mov_ids,
        format_func=lambda x: (
            f"ID {x} - {df_mov[df_mov['id_movimiento'] == x]['fecha'].values[0]}"
            f" - {df_mov[df_mov['id_movimiento'] == x]['tipo_movimiento'].values[0]} "
            f" - ${df_mov[df_mov['id_movimiento'] == x]['monto'].values[0]} ("
            f"{df_mov[df_mov['id_movimiento'] == x]['descripcion'].values[0]})"
        ),
    )

    if mov_seleccionado:
      conn = sqlite3.connect(DB_NAME)
      mov_data = pd.read_sql_query(
          f"SELECT * FROM movimientos WHERE id_movimiento = {mov_seleccionado}",
          conn,
      ).iloc[0]
      cuentas_df = pd.read_sql_query(
          "SELECT id_cuenta, nombre_cuenta FROM cuentas ORDER BY tipo_cuenta ASC,"
          " nombre_cuenta ASC",
          conn,
      )
      categorias_df = pd.read_sql_query(
          "SELECT id_categoria, nombre, tipo FROM categorias ORDER BY nombre ASC",
          conn,
      )
      conn.close()

      col_edit, col_del = st.columns([3, 1])

      with col_edit:
        tipos_movs_opc = ["Ingreso", "Egreso", "Transferencia"]
        idx_tipo_def = (
            tipos_movs_opc.index(mov_data["tipo_movimiento"])
            if mov_data["tipo_movimiento"] in tipos_movs_opc
            else 0
        )
        e_tipo_mov = st.selectbox(
            "Tipo de Movimiento",
            tipos_movs_opc,
            index=idx_tipo_def,
            key=f"edit_tipo_{mov_seleccionado}",
        )

        with st.form("form_edit_mov"):
          e_fecha = st.date_input(
              "Fecha",
              value=datetime.strptime(mov_data["fecha"], "%Y-%m-%d").date(),
          )

          e_cuenta_origen = None
          e_cuenta_destino = None
          e_id_cat = None

          if e_tipo_mov in ["Egreso", "Transferencia"]:
            orig_idx = 0
            if pd.notna(mov_data["id_cuenta_origen"]):
              matches = cuentas_df[
                  cuentas_df["id_cuenta"] == mov_data["id_cuenta_origen"]
              ].index
              if len(matches) > 0:
                orig_idx = list(cuentas_df["id_cuenta"]).index(
                    mov_data["id_cuenta_origen"]
                )
            e_cuenta_origen = st.selectbox(
                "Cuenta de Origen",
                options=cuentas_df["id_cuenta"].tolist(),
                index=orig_idx,
                format_func=lambda x: cuentas_df[cuentas_df["id_cuenta"] == x][
                    "nombre_cuenta"
                ].values[0],
            )

          if e_tipo_mov in ["Ingreso", "Transferencia"]:
            dest_idx = 0
            if pd.notna(mov_data["id_cuenta_destino"]):
              matches = cuentas_df[
                  cuentas_df["id_cuenta"] == mov_data["id_cuenta_destino"]
              ].index
              if len(matches) > 0:
                dest_idx = list(cuentas_df["id_cuenta"]).index(
                    mov_data["id_cuenta_destino"]
                )
            e_cuenta_destino = st.selectbox(
                "Cuenta de Destino",
                options=cuentas_df["id_cuenta"].tolist(),
                index=dest_idx,
                format_func=lambda x: cuentas_df[cuentas_df["id_cuenta"] == x][
                    "nombre_cuenta"
                ].values[0],
            )

          if e_tipo_mov != "Transferencia":
            cat_filtradas = categorias_df[
                (categorias_df["tipo"] == e_tipo_mov)
                | (categorias_df["tipo"] == "Ambos")
            ]
            cat_idx = 0
            if pd.notna(mov_data["id_categoria"]) and not cat_filtradas.empty:
              if (
                  mov_data["id_categoria"]
                  in cat_filtradas["id_categoria"].tolist()
              ):
                cat_idx = list(cat_filtradas["id_categoria"]).index(
                    mov_data["id_categoria"]
                )
            if not cat_filtradas.empty:
              e_id_cat = st.selectbox(
                  "Categoría",
                  options=cat_filtradas["id_categoria"].tolist(),
                  index=cat_idx,
                  format_func=lambda x: cat_filtradas[
                      cat_filtradas["id_categoria"] == x
                  ]["nombre"].values[0],
              )

          e_monto = st.number_input(
              "Monto ($)", value=float(mov_data["monto"]), step=100.0
          )
          e_estado = st.selectbox(
              "Estado",
              ["Pagado", "Pendiente"],
              index=0 if mov_data["estado"] == "Pagado" else 1,
          )
          e_desc = st.text_input(
              "Descripción", value=str(mov_data["descripcion"] or "")
          )

          btn_update = st.form_submit_button("Guardar Cambios en Movimiento")

          if btn_update:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute(
                """
                            UPDATE movimientos 
                            SET tipo_movimiento = ?, fecha = ?, id_cuenta_origen = ?, id_cuenta_destino = ?, id_categoria = ?, monto = ?, estado = ?, descripcion = ?
                            WHERE id_movimiento = ?
                        """,
                (
                    e_tipo_mov,
                    str(e_fecha),
                    e_cuenta_origen,
                    e_cuenta_destino,
                    e_id_cat,
                    e_monto,
                    e_estado,
                    e_desc,
                    mov_seleccionado,
                ),
            )
            conn.commit()
            conn.close()
            st.success("¡Movimiento actualizado con éxito!")
            st.rerun()

      with col_del:
        st.write("🗑️ **Eliminar**")
        if st.button("Eliminar este Movimiento"):
          conn = sqlite3.connect(DB_NAME)
          cursor = conn.cursor()
          cursor.execute(
              "DELETE FROM movimientos WHERE id_movimiento = ?",
              (mov_seleccionado,),
          )
          conn.commit()
          conn.close()
          st.warning("Movimiento eliminado.")
          st.rerun()

  else:
    st.info("Aún no hay movimientos cargados.")

# --- SECCIÓN 4: ADMINISTRAR CUENTAS Y CATEGORÍAS ---
elif menu == "Administrar Cuentas y Categorías":
  st.header("⚙️ Gestión de Cuentas y Categorías")

  tab1, tab2 = st.tabs(
      ["➕ Crear/Editar Cuentas", "🏷️ Crear/Editar Categorías"]
  )

  with tab1:
    col_c1, col_c2 = st.columns(2)
    with col_c1:
      st.subheader("➕ Nueva Cuenta")
      with st.form("form_alta_cuenta"):
        nombre_cuenta = st.text_input("Nombre de Cuenta")
        tipo_cuenta = st.selectbox(
            "Tipo",
            [
                "Banco",
                "Billetera Virtual",
                "Efectivo",
                "Inversión/Plazo Fijo",
                "Otro",
            ],
        )
        saldo_inicial = st.number_input(
            "Saldo Inicial", min_value=0.0, step=100.0
        )
        cotizacion = st.number_input(
            "Cotización", value=1.0, step=1.0, format="%.2f"
        )
        btn_cuenta = st.form_submit_button("Crear Cuenta")

        if btn_cuenta:
          if nombre_cuenta.strip() != "":
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO cuentas (nombre_cuenta, tipo_cuenta,"
                " saldo_inicial, cotizacion) VALUES (?, ?, ?, ?)",
                (nombre_cuenta, tipo_cuenta, saldo_inicial, cotizacion),
            )
            conn.commit()
            conn.close()
            st.success(f"¡Cuenta '{nombre_cuenta}' creada!")
            st.rerun()

    with col_c2:
      st.subheader("✏️ Editar Cuenta Existente")
      df_c = consultar_sql(
          "SELECT * FROM cuentas ORDER BY tipo_cuenta ASC, nombre_cuenta ASC"
      )
      if not df_c.empty:
        id_c_sel = st.selectbox(
            "Seleccioná la cuenta a modificar",
            options=df_c["id_cuenta"].tolist(),
            format_func=lambda x: df_c[df_c["id_cuenta"] == x][
                "nombre_cuenta"
            ].values[0],
        )

        cta_data = df_c[df_c["id_cuenta"] == id_c_sel].iloc[0]

        with st.form("form_edit_cuenta"):
          edit_n_cuenta = st.text_input(
              "Nombre de Cuenta", value=cta_data["nombre_cuenta"]
          )

          tipos_cuentas = [
              "Banco",
              "Billetera Virtual",
              "Efectivo",
              "Inversión/Plazo Fijo",
              "Otro",
          ]
          idx_cta = (
              tipos_cuentas.index(cta_data["tipo_cuenta"])
              if cta_data["tipo_cuenta"] in tipos_cuentas
              else 0
          )

          edit_t_cuenta = st.selectbox(
              "Tipo de Cuenta", tipos_cuentas, index=idx_cta
          )
          edit_s_inicial = st.number_input(
              "Saldo Inicial", value=float(cta_data["saldo_inicial"]), step=100.0
          )

          val_cot = (
              float(cta_data["cotizacion"])
              if "cotizacion" in cta_data and pd.notna(cta_data["cotizacion"])
              else 1.0
          )
          edit_cotizacion = st.number_input(
              "Cotización", value=val_cot, step=1.0, format="%.2f"
          )

          cols_btn = st.columns(2)
          btn_mod_c = cols_btn[0].form_submit_button("Actualizar Cuenta")
          btn_del_c = cols_btn[1].form_submit_button("🗑️ Eliminar Cuenta")

          if btn_mod_c:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute(
                """
                            UPDATE cuentas 
                            SET nombre_cuenta = ?, tipo_cuenta = ?, saldo_inicial = ?, cotizacion = ?
                            WHERE id_cuenta = ?
                        """,
                (
                    edit_n_cuenta,
                    edit_t_cuenta,
                    edit_s_inicial,
                    edit_cotizacion,
                    id_c_sel,
                ),
            )
            conn.commit()
            conn.close()
            st.success("¡Cuenta modificada!")
            st.rerun()

          if btn_del_c:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM cuentas WHERE id_cuenta = ?", (id_c_sel,)
            )
            conn.commit()
            conn.close()
            st.warning("Cuenta eliminada.")
            st.rerun()

  with tab2:
    col_cat1, col_cat2 = st.columns(2)
    with col_cat1:
      st.subheader("➕ Nueva Categoría")
      with st.form("form_alta_cat"):
        nombre_cat = st.text_input("Nombre de Categoría")
        tipo_cat = st.selectbox(
            "Tipo de Categoría", ["Ingreso", "Egreso", "Ambos"]
        )
        btn_cat = st.form_submit_button("Crear Categoría")

        if btn_cat:
          if nombre_cat.strip() != "":
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO categorias (nombre, tipo) VALUES (?, ?)",
                (nombre_cat, tipo_cat),
            )
            conn.commit()
            conn.close()
            st.success(f"¡Categoría '{nombre_cat}' creada!")
            st.rerun()

    with col_cat2:
      st.subheader("✏️ Editar Categoría Existente")
      df_cat = consultar_sql("SELECT * FROM categorias ORDER BY nombre ASC")
      if not df_cat.empty:
        id_cat_sel = st.selectbox(
            "Seleccioná la categoría a modificar",
            options=df_cat["id_categoria"].tolist(),
            format_func=lambda x: df_cat[df_cat["id_categoria"] == x][
                "nombre"
            ].values[0],
        )

        cat_data = df_cat[df_cat["id_categoria"] == id_cat_sel].iloc[0]

        with st.form("form_edit_cat"):
          edit_n_cat = st.text_input(
              "Nombre de Categoría", value=cat_data["nombre"]
          )

          opciones_tipo_cat = ["Ingreso", "Egreso", "Ambos"]
          tipo_actual_cat = cat_data["tipo"]
          idx_cat_def = (
              opciones_tipo_cat.index(tipo_actual_cat)
              if tipo_actual_cat in opciones_tipo_cat
              else 0
          )

          edit_t_cat = st.selectbox(
              "Tipo de Categoría", opciones_tipo_cat, index=idx_cat_def
          )

          cols_btn_cat = st.columns(2)
          btn_mod_cat = cols_btn_cat[0].form_submit_button(
              "Actualizar Categoría"
          )
          btn_del_cat = cols_btn_cat[1].form_submit_button("🗑️ Eliminar Categoría")

          if btn_mod_cat:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute(
                """
                            UPDATE categorias 
                            SET nombre = ?, tipo = ?
                            WHERE id_categoria = ?
                        """,
                (edit_n_cat, edit_t_cat, id_cat_sel),
            )
            conn.commit()
            conn.close()
            st.success("¡Categoría modificada!")
            st.rerun()

          if btn_del_cat:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM categorias WHERE id_categoria = ?", (id_cat_sel,)
            )
            conn.commit()
            conn.close()
            st.warning("Categoría eliminada.")
            st.rerun()