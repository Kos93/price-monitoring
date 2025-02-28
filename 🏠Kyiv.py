import streamlit as st
import pandas as pd
import re
from streamlit_gsheets import GSheetsConnection
from st_aggrid import AgGrid, GridOptionsBuilder
import locale

try:
    locale.setlocale(locale.LC_ALL, 'uk_UA.UTF-8')
except:
    try:
        locale.setlocale(locale.LC_ALL, 'uk_UA')
    except:
        st.warning("Не вдалося встановити українську локаль. Використовується системна локаль.")

st.set_page_config(
    page_title="Київ",
    page_icon="📈",
    layout="wide"
)



col1, col2 = st.columns(2)

with col1:
    st.title("Київ ціни")

    # Підключення до Google Sheets
    url = "1IdRGszdGFp9cqn3gD5bD1UJmUMSEe088Ov4T_7_GRn4"  # Посилання (ID) вашої таблиці
    conn = st.connection("gsheets", type=GSheetsConnection)
    data = conn.read(spreadsheet=url, usecols=None)

    # Прибираємо стовпець 'id', якщо він існує
    if 'id' in data.columns:
        data.drop(columns='id', inplace=True)

    first_col = data.columns[0]
    gb = GridOptionsBuilder.from_dataframe(data)
    gb.configure_column(first_col, pinned='left', filter='agSetColumnFilter')
    gridOptions = gb.build()

    AgGrid(data, gridOptions=gridOptions)

    # Визначаємо, які стовпці є датами (формат dd.mm.yyyy)
    date_pattern = r'^\d{2}\.\d{2}\.\d{4}$'
    date_columns = [col for col in data.columns if isinstance(col, str) and re.match(date_pattern, col)]

    # Стовпці, які не є датами (коригуйте під свою структуру)
    id_vars = [col for col in data.columns if col not in date_columns]

    # Перетворюємо з "широкого" формату в "довгий"
    try:
        long_df = data.melt(
            id_vars=id_vars,
            value_vars=date_columns,
            var_name="Дата",
            value_name="Ціна"
        )
    except Exception as e:
        st.error(f"Помилка при перетворенні даних: {e}")
        st.stop()

    # Очищаємо значення цін (замінюємо коми на крапки і видаляємо нечислові символи)
    long_df["Ціна"] = long_df["Ціна"].astype(str).str.replace(',', '.').str.replace(r'[^\d.]', '', regex=True)
    
    # Конвертуємо "Дата" у datetime
    long_df["Дата"] = pd.to_datetime(long_df["Дата"], format="%d.%m.%Y", errors="coerce")

    # Конвертуємо "Ціна" у float з обробкою помилок
    long_df["Ціна"] = pd.to_numeric(long_df["Ціна"], errors="coerce")

    # Видаляємо рядки з відсутніми цінами або датами
    long_df = long_df.dropna(subset=["Дата", "Ціна"])

    # Віджети для вибору товарів і діапазону дат
    available_products = long_df["Товар"].unique().tolist()

    min_date = long_df["Дата"].min()
    max_date = long_df["Дата"].max()

    # Перевірка наявності дат
    if pd.isna(min_date) or pd.isna(max_date):
        st.error("Помилка у датах. Перевірте формат дат у таблиці.")
        st.stop()

    date_range = st.date_input(
        label="Виберіть початкову і кінцеву дати:",
        value=[min_date, max_date],
        min_value=min_date,
        max_value=max_date,
        format="DD.MM.YYYY"
    )

    # Перевірка, що вибрано дві дати
    if len(date_range) < 2:
        st.warning("Будь ласка, виберіть початкову та кінцеву дати (два значення).")
        st.stop()
    else:
        start_date, end_date = date_range

    # Захист від занадто великих діапазонів дат
    days_diff = (end_date - start_date).days
    if days_diff > 730:
        st.warning(f"Вибраний діапазон ({days_diff} днів) занадто великий. Рекомендується вибрати менший період (до 730 днів).")

    selected_products = st.multiselect(
        "Оберіть позиції (Товар) для аналізу:",
        options=available_products,
        default=available_products[:2] if len(available_products) >= 2 else available_products[:1]
    )

    # Перевірка наявності обраних товарів
    if not selected_products:
        st.warning("Будь ласка, оберіть хоча б один товар для аналізу.")
        st.stop()

    # Фільтр для побудови графіка
    filtered_for_chart = long_df[
        (long_df["Товар"].isin(selected_products)) &
        (long_df["Дата"] >= pd.to_datetime(start_date)) &
        (long_df["Дата"] <= pd.to_datetime(end_date))
    ].copy()

    if filtered_for_chart.empty:
        st.warning("Немає даних у вибраному діапазоні дат або для вибраних товарів.")
        st.stop()

    # Будуємо графік
    filtered_for_chart.sort_values(by=["Товар", "Дата"], inplace=True)
    
    # Перевірка на наявність повторюваних індексів перед створенням зведеної таблиці
    duplicate_check = filtered_for_chart.duplicated(subset=["Дата", "Товар"])
    if duplicate_check.any():
        # Усуваємо дублікати, залишаючи останнє значення
        st.warning(f"Виявлено {duplicate_check.sum()} дублікатів дат. Використовуються останні доступні значення.")
        filtered_for_chart = filtered_for_chart.drop_duplicates(subset=["Дата", "Товар"], keep="last")
    
    try:
        pivot_chart = filtered_for_chart.pivot(index="Дата", columns="Товар", values="Ціна")
        st.subheader("Графік динаміки цін")
        st.line_chart(pivot_chart)
    except Exception as e:
        st.error(f"Помилка при створенні графіка: {e}")
        st.write("Спробуйте вибрати інші товари або перевірте дані.")

    # Розрахунок початкової/кінцевої ціни
    results = []

    for product in selected_products:
        try:
            # Обробляємо кожен товар у захищеному блоці try-except
            product_data = filtered_for_chart[filtered_for_chart["Товар"] == product].copy()
            
            if product_data.empty:
                results.append({
                    "Товар": product,
                    "Початкова ціна": None,
                    "Кінцева ціна": None,
                    "Зміна, %": None,
                    "Середня ціна": None,
                    "Макс. ціна": None,
                    "Дата макс.": None
                })
                continue

            # Сортуємо за датою
            product_data.sort_values("Дата", inplace=True)
            
            # Створюємо "суцільний" ряд дат від start_date до end_date
            date_range_df = pd.DataFrame(
                index=pd.date_range(start=start_date, end=end_date, freq="D")
            )
            date_range_df.index.name = "Дата"
            
            # Підготовка даних для reindex
            product_prices = product_data.set_index("Дата")["Ціна"]
            
            # Обмежуємо розмір для запобігання проблем з пам'яттю
            if len(date_range_df) > 731:
                st.warning(f"Діапазон дат для {product} обмежено до 731 днів для запобігання зависанню.")
                date_range_df = date_range_df.iloc[:731]
            
            # Reindex з обмеженим заповненням пропусків
            reindexed_prices = product_prices.reindex(date_range_df.index)
            
            # Обмежене заповнення пропусків (максимум 30 днів)
            reindexed_prices = reindexed_prices.bfill(limit=30).ffill(limit=30)
            
            # Якщо все ще є пропуски, заповнюємо їх середнім значенням
            if reindexed_prices.isna().any():
                mean_price = product_prices.mean()
                reindexed_prices = reindexed_prices.fillna(mean_price)
            
            # Беремо значення на початок і кінець періоду
            initial_price = reindexed_prices.iloc[0] if not reindexed_prices.empty else None
            final_price = reindexed_prices.iloc[-1] if not reindexed_prices.empty and len(reindexed_prices) > 1 else initial_price
            
            # Розрахунок відсотка зміни
            if pd.isna(initial_price) or initial_price == 0 or pd.isna(final_price):
                percent_change = None
            else:
                percent_change = ((final_price - initial_price) / initial_price) * 100
            
            # Статистика
            avg_price = reindexed_prices.mean()
            max_price = reindexed_prices.max()
            
            if not pd.isna(max_price) and max_price > 0:
                max_indices = reindexed_prices[reindexed_prices == max_price].index
                if not max_indices.empty:
                    max_date = max_indices[0].strftime('%d.%m.%Y') # type: ignore
                else:
                    max_date = None
            else:
                max_date = None
            
            results.append({
                "Товар": product,
                "Початкова ціна": initial_price,
                "Кінцева ціна": final_price,
                "Зміна, %": round(percent_change, 1) if percent_change is not None else None,
                "Середня ціна": round(avg_price, 1) if not pd.isna(avg_price) else None,
                "Макс. ціна": max_price if not pd.isna(max_price) else None,
                "Дата макс.": max_date
            })
            
        except Exception as e:
            st.warning(f"Помилка при обробці товару '{product}': {str(e)}")
            results.append({
                "Товар": product,
                "Початкова ціна": None,
                "Кінцева ціна": None,
                "Зміна, %": None,
                "Середня ціна": None,
                "Макс. ціна": None,
                "Дата макс.": "Помилка обробки"
            })

    result_df = pd.DataFrame(results)

    # Кольорове виділення
    def highlight_change(val): # type: ignore
        if pd.isna(val):
            return "color: black;"
        elif val > 0:
            return "color: red;"
        elif val < 0:
            return "color: green;"
        else:
            return "color: black;"

    styled_result_df = (
        result_df
        .style
        .applymap(highlight_change, subset=["Зміна, %"]) # type: ignore
        .format("{:.2f}", subset=["Початкова ціна", "Кінцева ціна", "Зміна, %", "Середня ціна", "Макс. ціна"], na_rep="-")
    )

    st.subheader(f"Таблиця змін цін з {start_date.strftime('%d.%m.%Y')} по {end_date.strftime('%d.%m.%Y')}")
    st.dataframe(styled_result_df, use_container_width=True)

with col2:
    st.title("Київ кількість")

    # Connect to Google Sheets
    url = "1v_3O4PpGVFTji4YQvJEdsyJ3Dcx5Sqtjp7QvrqH36bk"  # Google Sheet ID
    conn = st.connection("gsheets", type=GSheetsConnection)
    
    try:
        data = conn.read(spreadsheet=url, usecols=None)
    except Exception as e:
        st.error(f"Помилка підключення до Google Sheets: {e}")
        st.stop()

    # Remove 'id' column if it exists
    if 'id' in data.columns:
        data.drop(columns='id', inplace=True)

    # Display the full table with AgGrid
    first_col = data.columns[0]
    gb = GridOptionsBuilder.from_dataframe(data)
    gb.configure_column(first_col, pinned='left', filter='agSetColumnFilter')
    gridOptions = gb.build()
    AgGrid(data, gridOptions=gridOptions)

    # Identify date columns (format dd.mm.yyyy)
    date_pattern = r'^\d{2}\.\d{2}\.\d{4}$'
    date_columns = [col for col in data.columns if isinstance(col, str) and re.match(date_pattern, col)]

    # Non-date columns (metadata)
    id_vars = [col for col in data.columns if col not in date_columns]

    # Hard limits for date selection
    hard_min_date = pd.to_datetime("2022-01-01")
    hard_max_date = pd.to_datetime("2025-12-31")

    # Convert wide format to long format
    if date_columns:
        try:
            long_df = pd.melt(
                data,
                id_vars=id_vars,
                value_vars=date_columns,
                var_name="Дата",
                value_name="Кількість"
            )
        except Exception as e:
            st.error(f"Помилка при перетворенні даних: {e}")
            st.stop()

        # Очищаємо значення кількості (замінюємо коми на крапки і видаляємо нечислові символи)
        long_df["Кількість"] = long_df["Кількість"].astype(str).str.replace(',', '.').str.replace(r'[^\d.]', '', regex=True)

        # Convert "Дата" to datetime
        long_df["Дата"] = pd.to_datetime(long_df["Дата"], format="%d.%m.%Y", errors="coerce")
        
        # Convert "Кількість" to numeric, coercing errors to NaN
        long_df["Кількість"] = pd.to_numeric(long_df["Кількість"], errors="coerce")
        
        # Remove rows with missing dates or quantities before filling
        long_df = long_df.dropna(subset=["Дата"])
        
        # Fill NaN with 0 for quantity
        long_df["Кількість"] = long_df["Кількість"].fillna(0)
        
        # Check real min and max dates in the data
        if not long_df.empty and not long_df["Дата"].isna().all():
            real_min_date = long_df["Дата"].min()
            real_max_date = long_df["Дата"].max()
            
            # Limit real dates by hard limits
            min_date = max(real_min_date, hard_min_date)
            max_date = min(real_max_date, hard_max_date)
            
            # Date selection widget
            date_range = st.date_input(
                label="Виберіть початкову і кінцеву дати:",
                value=[min_date, max_date],
                min_value=hard_min_date,
                max_value=hard_max_date,
                format="DD.MM.YYYY"
            )
            
            # Check that two dates are selected
            if len(date_range) < 2:
                st.warning("Будь ласка, виберіть початкову та кінцеву дати (два значення).")
                st.stop()
            else:
                start_date, end_date = date_range
            
            # Check that end_date is not earlier than start_date
            if end_date < start_date:
                st.warning("Кінцева дата не може бути раніше початкової.")
                st.stop()
            
            # Захист від занадто великих діапазонів дат
            days_diff = (end_date - start_date).days
            if days_diff > 730:
                st.warning(f"Вибраний діапазон ({days_diff} днів) занадто великий. Рекомендується вибрати менший період (до 730 днів).")
            
            # Product selection
            product_column = "Товар" if "Товар" in id_vars else id_vars[0]
            available_products = long_df[product_column].unique().tolist()
            
            selected_products = st.multiselect(
                f"Оберіть позиції ({product_column}) для аналізу:",
                options=available_products,
                default=available_products[:min(2, len(available_products))]
            )
            
            if selected_products:
                # Filter data for chart
                filtered_for_chart = long_df[
                    (long_df[product_column].isin(selected_products)) &
                    (long_df["Дата"] >= pd.to_datetime(start_date)) &
                    (long_df["Дата"] <= pd.to_datetime(end_date))
                ].copy()
                
                if not filtered_for_chart.empty:
                    filtered_for_chart.sort_values(by=[product_column, "Дата"], inplace=True)
                    
                    # Перевірка на наявність повторюваних індексів перед створенням зведеної таблиці
                    duplicate_check = filtered_for_chart.duplicated(subset=["Дата", product_column])
                    if duplicate_check.any():
                        # Усуваємо дублікати, залишаючи останнє значення
                        st.warning(f"Виявлено {duplicate_check.sum()} дублікатів дат. Використовуються останні доступні значення.")
                        filtered_for_chart = filtered_for_chart.drop_duplicates(subset=["Дата", product_column], keep="last")
                    
                    try:
                        # Convert to wide format for chart
                        pivot_chart = filtered_for_chart.pivot(index="Дата", columns=product_column, values="Кількість")
                        
                        st.subheader("Графік динаміки кількості")
                        st.line_chart(pivot_chart)
                    except Exception as e:
                        st.error(f"Помилка при створенні графіка: {e}")
                        st.write("Спробуйте вибрати інші товари або перевірте дані.")
                    
                    # Calculate initial/final quantities and changes
                    results = []
                    
                    calc_df = long_df[long_df[product_column].isin(selected_products)].copy()
                    
                    for product in selected_products:
                        try:
                            product_data = calc_df[calc_df[product_column] == product].copy()
                            
                            if product_data.empty:
                                results.append({
                                    product_column: product,
                                    "Початкова кількість": None,
                                    "Кінцева кількість": None,
                                    "Зміна, %": None,
                                    "Середня кількість": None,
                                    "Макс. кількість": None,
                                    "Дата макс.": None
                                })
                                continue
                            
                            product_data.sort_values("Дата", inplace=True)
                            
                            # Створюємо "суцільний" ряд дат від start_date до end_date
                            date_range_df = pd.DataFrame(
                                index=pd.date_range(start=start_date, end=end_date, freq="D")
                            )
                            date_range_df.index.name = "Дата"
                            
                            # Підготовка даних для reindex
                            product_quantities = product_data.set_index("Дата")["Кількість"]
                            
                            # Обмежуємо розмір для запобігання проблем з пам'яттю
                            if len(date_range_df) > 731:
                                st.warning(f"Діапазон дат для {product} обмежено до 731 днів для запобігання зависанню.")
                                date_range_df = date_range_df.iloc[:731]
                            
                            # Reindex з обмеженим заповненням пропусків
                            reindexed_quantities = product_quantities.reindex(date_range_df.index)
                            
                            # Обмежене заповнення пропусків (максимум 30 днів)
                            reindexed_quantities = reindexed_quantities.bfill(limit=30).ffill(limit=30)
                            
                            # Якщо все ще є пропуски, заповнюємо їх середнім значенням або нулем
                            if reindexed_quantities.isna().any():
                                if product_quantities.count() > 0:
                                    mean_quantity = product_quantities.mean()
                                    reindexed_quantities = reindexed_quantities.fillna(mean_quantity)
                                else:
                                    reindexed_quantities = reindexed_quantities.fillna(0)
                            
                            # Initial and final values
                            initial_qty = reindexed_quantities.iloc[0] if not reindexed_quantities.empty else 0
                            final_qty = reindexed_quantities.iloc[-1] if not reindexed_quantities.empty and len(reindexed_quantities) > 1 else initial_qty
                            
                            # Calculate percentage change - improved to handle zero initial values
                            if pd.isna(initial_qty) or pd.isna(final_qty):
                                percent_change = None
                                status = "Немає даних"
                            elif initial_qty == 0 and final_qty == 0:
                                percent_change = 0
                                status = "Стабільно"
                            elif initial_qty == 0 and final_qty > 0:
                                percent_change = 100  # Instead of infinity, mark as 100% (new item)
                                status = "Новий товар"
                            elif initial_qty > 0 and final_qty == 0:
                                percent_change = -100  # Complete reduction
                                status = "Повністю видалено"
                            else:
                                percent_change = ((final_qty - initial_qty) / initial_qty) * 100
                                
                                if percent_change > 10:
                                    status = "Значне збільшення"
                                elif percent_change > 0:
                                    status = "Збільшення"
                                elif percent_change < -10:
                                    status = "Значне зменшення"
                                elif percent_change < 0:
                                    status = "Зменшення"
                                else:
                                    status = "Стабільно"
                            
                            # Additional metrics
                            avg_qty = reindexed_quantities.mean() if not reindexed_quantities.empty else 0
                            max_qty = reindexed_quantities.max() if not reindexed_quantities.empty else 0
                            
                            # Find the date of maximum quantity
                            if max_qty > 0 and not pd.isna(max_qty):
                                max_indices = reindexed_quantities[reindexed_quantities == max_qty].index
                                if not max_indices.empty:
                                    max_date = max_indices[0].strftime('%d.%m.%Y')
                                else:
                                    max_date = None
                            else:
                                max_date = None
                            
                            results.append({
                                product_column: product,
                                "Початкова кількість": initial_qty,
                                "Кінцева кількість": final_qty,
                                "Зміна, %": round(percent_change, 1) if percent_change is not None else None,
                                "Середня кількість": round(avg_qty, 1) if not pd.isna(avg_qty) else None,
                                "Макс. кількість": max_qty if not pd.isna(max_qty) else None,
                                "Дата макс.": max_date
                            })
                        
                        except Exception as e:
                            st.warning(f"Помилка при обробці товару '{product}': {str(e)}")
                            results.append({
                                product_column: product,
                                "Початкова кількість": None,
                                "Кінцева кількість": None,
                                "Зміна, %": None,
                                "Середня кількість": None,
                                "Макс. кількість": None,
                                "Дата макс.": "Помилка обробки"
                            })
                    
                    result_df = pd.DataFrame(results)
                    
                    # Color highlighting for changes
                    def highlight_change(val, attr):
                        if attr != "Зміна, %":
                            return ""
                        
                        if pd.isna(val):
                            return "color: black;"
                        elif val > 20:
                            return "color: green; font-weight: bold"
                        elif val > 0:
                            return "color: green"
                        elif val < -20:
                            return "color: red; font-weight: bold"
                        elif val < 0:
                            return "color: red"
                        else:
                            return "color: gray"
                    
                    # Apply styling
                    styled_df = result_df.style
                    
                    # Apply highlighting for "Зміна, %" column
                    if "Зміна, %" in result_df.columns:
                        styled_df = styled_df.applymap(
                            lambda val, attr=None: highlight_change(val, attr),
                            subset=["Зміна, %"]
                        )
                    
                    # Format numbers
                    styled_df = styled_df.format({
                        "Початкова кількість": "{:.2f}",
                        "Кінцева кількість": "{:.2f}",
                        "Зміна, %": "{:.1f}%",
                        "Середня кількість": "{:.2f}",
                        "Макс. кількість": "{:.2f}"
                    }, na_rep="-")
                    
                    st.subheader(f"Таблиця змін з {start_date.strftime('%d.%m.%Y')} по {end_date.strftime('%d.%m.%Y')}")
                    st.dataframe(styled_df, use_container_width=True)
                    
                else:
                    st.warning("Немає даних у вибраному діапазоні дат або для вибраних позицій.")
            else:
                st.warning(f"Будь ласка, оберіть принаймні одну позицію для аналізу.")
        else:
            st.warning("Немає коректних дат у таблиці.")
    else:
        st.warning("Не знайдено стовпців з датами у форматі DD.MM.YYYY")