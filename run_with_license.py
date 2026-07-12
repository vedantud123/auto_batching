from auto_batching_pi import AutoBatchingDesktop, restart_apache


def main():
    restart_apache()
    app = AutoBatchingDesktop()
    app.run()


if __name__ == '__main__':
    main()
