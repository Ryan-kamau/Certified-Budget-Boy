#CLI daashboard graphs using matplotlib
import matplotlib.pyplot as plt

def show_dashboard_graph():
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun"]
    income = [3000, 3200, 3100, 3500, 3700, 4000]
    expenses = [2000, 2100, 1900, 2500, 2400, 2600]

    plt.figure()
    plt.plot(months, income)
    plt.plot(months, expenses)

    plt.title("Income vs Expense Trend")
    plt.xlabel("Month")
    plt.ylabel("Amount")
    plt.legend(["Income", "Expenses"])

    plt.show()

if __name__ == "__main__":
    show_dashboard_graph()