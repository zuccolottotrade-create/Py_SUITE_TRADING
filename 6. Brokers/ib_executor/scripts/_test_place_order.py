from ib_executor import IBExecutor

def main():
    ex = IBExecutor()  # host/port/clientId da env o default
    with ex:
        c = ex.contract_stock("AAPL", "USD", "SMART")
        t = ex.place_market(c, "BUY", 1)
        ex.wait_done(t, timeout_sec=10)
        print(ex.trade_snapshot(t))

if __name__ == "__main__":
    main()
