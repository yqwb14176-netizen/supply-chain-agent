import numpy as np
import pandas as pd
import streamlit as st

# إعدادات الصفحة
st.set_page_config(
    page_title="مساعد سلاسل الإمداد - عبايات", page_icon="🧵", layout="wide"
)

st.title("🧵 محرك تحليل المخزون وسلاسل الإمداد - عبايات")
st.markdown(
    "نظام آلي لحساب أيام تغطية المخزون (DOI)، نقطة إعادة الطلب (ROP)، وإعادة"
    " التوزيع بين الفروع."
)

# شريط جانبي لرفع الملفات
st.sidebar.header("📁 رفع بيانات النظام (ERP)")
sales_file = st.sidebar.file_uploader(
    "1. تقرير المبيعات (Sales_Data.xlsx)", type=["xlsx", "csv"]
)
stock_file = st.sidebar.file_uploader(
    "2. تقرير المخزون الحالي (Current_Stock.xlsx)", type=["xlsx", "csv"]
)
master_file = st.sidebar.file_uploader(
    "3. بيانات التشغيل والإنتاج (Supply_Master.xlsx)", type=["xlsx", "csv"]
)

if sales_file and stock_file and master_file:
  try:
    # 1. قراءة البيانات
    df_sales = (
        pd.read_csv(sales_file)
        if sales_file.name.endswith(".csv")
        else pd.read_excel(sales_file)
    )
    df_stock = (
        pd.read_csv(stock_file)
        if stock_file.name.endswith(".csv")
        else pd.read_excel(stock_file)
    )
    df_master = (
        pd.read_csv(master_file)
        if master_file.name.endswith(".csv")
        else pd.read_excel(master_file)
    )

    # تحويل التواريخ لحساب عدد الأيام الإجمالي في تقرير المبيعات
    df_sales["Date"] = pd.to_datetime(df_sales["Date"])
    total_days = (df_sales["Date"].max() - df_sales["Date"].min()).days + 1
    total_days = max(total_days, 1)  # تجنب القسمة على صفر

    st.sidebar.success(f"تم تحليل بيانات مبيعات لـ {total_days} يوم/أيام.")

    # ----------------------------------------------------
    # 2. الخوارزميات الحسابية (Data Processing Engine)
    # ----------------------------------------------------

    # أ) حساب متوسط البيع اليومي لكل موديل في كل فرع
    branch_sales_avg = (
        df_sales.groupby(["Branch_Name", "SKU"])["Qty_Sold"]
        .sum()
        .reset_index()
    )
    branch_sales_avg["Daily_Sales_Rate"] = (
        branch_sales_avg["Qty_Sold"] / total_days
    )

    # ب) حساب متوسط البيع اليومي الإجمالي لكل موديل (كافة الفروع)
    total_sales_avg = (
        df_sales.groupby("SKU")["Qty_Sold"]
        .sum()
        .reset_index(name="Total_Qty_Sold")
    )
    total_sales_avg["Total_Daily_Rate"] = (
        total_sales_avg["Total_Qty_Sold"] / total_days
    )

    # ج) دمج المخزون مع المبيعات والمستر لحساب DOI لكل فرع
    stock_analysis = pd.merge(
        df_stock, branch_sales_avg, on=["Branch_Name", "SKU"], how="left"
    ).fillna({"Daily_Sales_Rate": 0, "Qty_Sold": 0})

    # حساب DOI لكل فرع
    stock_analysis["DOI"] = np.where(
        stock_analysis["Daily_Sales_Rate"] > 0,
        stock_analysis["Current_Stock"] / stock_analysis["Daily_Sales_Rate"],
        999,  # رمز للركود إذا كان البيع صفراً
    )

    # د) حساب ROP على مستوى الشركة ككل (Master Level)
    master_analysis = pd.merge(df_master, total_sales_avg, on="SKU", how="left")
    master_analysis = pd.merge(
        master_analysis,
        df_stock.groupby("SKU")["Current_Stock"].sum().reset_index(),
        on="SKU",
        how="left",
    ).fillna({"Total_Daily_Rate": 0, "Current_Stock": 0})

    # تطبيق معادلة ROP
    master_analysis["ROP"] = (
        master_analysis["Total_Daily_Rate"] * master_analysis["Lead_Time_Days"]
    ) + master_analysis.get("Safety_Stock", 0)

    # حساب النقص الفعلي والكميات المقترحة للإنتاج
    master_analysis["Total_Pipeline"] = (
        master_analysis["Current_Stock"]
        + master_analysis.get("In_Production_Qty", 0)
        + master_analysis.get("In_Transit_Qty", 0)
    )
    master_analysis["Production_Needed"] = np.maximum(
        0, master_analysis["ROP"] - master_analysis["Total_Pipeline"]
    )

    # ----------------------------------------------------
    # 3. عرض النتائج في واجهة المستخدم
    # ----------------------------------------------------

    tab1, tab2, tab3 = st.tabs([
        "📊 المؤشرات العامة والركود",
        "🔄 النقل المتبادل بين الفروع",
        "🏭 أوامر الإنتاج (ROP)",
    ])

    with tab1:
      st.subheader("تحليل أيام تغطية المخزون (DOI)")
      col1, col2, col3 = st.columns(3)
      col1.metric("إجمالي القطع المباعة", int(df_sales["Qty_Sold"].sum()))
      col2.metric("إجمالي المخزون الحالي", int(df_stock["Current_Stock"].sum()))

      slow_movers = stock_analysis[
          (stock_analysis["DOI"] > 40) & (stock_analysis["Current_Stock"] > 5)
      ]
      col3.metric("عدد الموديلات الراكدة بالفروع", len(slow_movers))

      st.write("### تفاصيل المخزون ومعدل التغطية لكل فرع:")
      st.dataframe(
          stock_analysis[
              ["Branch_Name", "SKU", "Current_Stock", "Daily_Sales_Rate", "DOI"]
          ].sort_values(by="DOI", ascending=False)
      )

    with tab2:
      st.subheader("توصيات النقل بين الفروع لتفادي العجز")
      st.caption(
          "تعتمد الخوارزمية على نقل البضاعة من الفروع ذات التغطية العالية (DOI >"
          " 40 يوم) إلى الفروع التي تعاني من عجز (DOI < 7 أيام)."
      )

      surplus_branches = stock_analysis[stock_analysis["DOI"] > 40]
      deficit_branches = stock_analysis[stock_analysis["DOI"] < 7]

      transfer_suggestions = []

      for _, deficit in deficit_branches.iterrows():
        sku = deficit["SKU"]
        matching_surplus = surplus_branches[surplus_branches["SKU"] == sku]

        for _, surplus in matching_surplus.iterrows():
          transfer_qty = min(
              int(surplus["Current_Stock"] * 0.5), 10
          )  # اقتراح نقل 50% من الفائض
          if transfer_qty > 0:
            transfer_suggestions.append({
                "SKU": sku,
                "من فرع (فائض)": surplus["Branch_Name"],
                "إلى فرع (عجز)": deficit["Branch_Name"],
                "الكمية المقترحة للنقل": transfer_qty,
                "أيام تغطية المصدر": round(surplus["DOI"], 1),
                "أيام تغطية الهدف": round(deficit["DOI"], 1),
            })

      df_transfers = pd.DataFrame(transfer_suggestions)
      if not df_transfers.empty:
        st.dataframe(df_transfers)
      else:
        st.success(
            "لا توجد حالات عجز وفائض متطابقة تتطلب النقل المباشر حالياً."
        )

    with tab3:
      st.subheader("جدول أوامر الإنتاج وإعادة الطلب (ROP)")
      production_orders = master_analysis[master_analysis["Production_Needed"] > 0]

      if not production_orders.empty:
        st.warning(f"توجد {len(production_orders)} موديلات تتطلب فتح أمر إنتاج فوراً!")
        st.dataframe(
            production_orders[[
                "SKU",
                "Total_Daily_Rate",
                "Current_Stock",
                "ROP",
                "Production_Needed",
            ]]
            .rename(columns={
                "Total_Daily_Rate": "معدل البيع اليومي الإجمالي",
                "Current_Stock": "المخزون الحالي",
                "ROP": "نقطة إعادة الطلب (ROP)",
                "Production_Needed": "الكمية المطلوبة للإنتاج",
            })
            .sort_values(by="الكمية المطلوبة للإنتاج", ascending=False)
        )
      else:
        st.success("جميع الموديلات تتجاوز نقطة الأمان ROP، لا توجد حاجة لإنتاج جديد حالياً.")

  except Exception as e:
    st.error(f"حدث خطأ أثناء معالجة الحسابات: {e}")

else:
  st.info("الرجاء رفع الملفات الثلاثة من القائمة الجانبية في اليسار لبدء الحسابات.")
