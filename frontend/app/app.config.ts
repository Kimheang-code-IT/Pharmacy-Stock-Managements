export default defineAppConfig({
  ui: {
    colors: {
      primary: 'teal',
      secondary: 'navy',
      neutral: 'zinc',
    },

    /** Route top-bar / toast progress / loaders follow brand primary. */
    progress: {
      defaultVariants: {
        color: 'primary',
        size: 'sm',
        animation: 'carousel',
      },
    },

    toast: {
      defaultVariants: {
        color: 'primary',
      },
    },

    /**
     * Global form control look for operational forms:
     * soft elevated fill, no hard ring, rounded-sm.
     * Applies to Input / Select / Textarea / InputDate / InputNumber / Checkbox / FormField.
     */
    formField: {
      slots: {
        root: 'w-full',
        container: 'w-full',
        label: 'block text-sm font-medium text-toned',
        help: 'mt-1.5 text-xs text-muted leading-relaxed',
        error: 'mt-1.5 text-xs text-error',
        hint: 'text-xs text-muted',
        description: 'text-xs text-muted',
      },
    },

    input: {
      variants: {
        variant: {
          soft: 'text-highlighted bg-elevated/70 hover:bg-elevated focus:bg-elevated focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary focus-visible:outline-none disabled:bg-elevated/50 disabled:opacity-75 disabled:focus-visible:ring-0',
        },
      },
      defaultVariants: {
        size: 'md',
        color: 'primary',
        variant: 'soft',
      },
    },

    textarea: {
      variants: {
        variant: {
          soft: 'text-highlighted bg-elevated/70 hover:bg-elevated focus:bg-elevated focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary focus-visible:outline-none disabled:bg-elevated/50 disabled:opacity-75 disabled:focus-visible:ring-0',
        },
      },
      defaultVariants: {
        size: 'md',
        color: 'primary',
        variant: 'soft',
      },
    },

    select: {
      variants: {
        variant: {
          soft: 'text-highlighted bg-elevated/70 hover:bg-elevated focus:bg-elevated focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary focus-visible:outline-none disabled:bg-elevated/50 disabled:opacity-75 disabled:focus-visible:ring-0',
        },
      },
      defaultVariants: {
        size: 'md',
        color: 'primary',
        variant: 'soft',
      },
    },

    selectMenu: {
      slots: {
        // Override default inline-flex shrink-to-content so dialog/forms fill width.
        base: 'relative group rounded-md flex w-full items-center disabled:cursor-not-allowed disabled:opacity-75 transition-colors',
      },
      variants: {
        variant: {
          soft: 'text-highlighted bg-elevated/70 hover:bg-elevated focus:bg-elevated focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary focus-visible:outline-none disabled:bg-elevated/50 disabled:opacity-75 disabled:focus-visible:ring-0',
        },
      },
      defaultVariants: {
        size: 'md',
        color: 'primary',
        variant: 'soft',
      },
    },

    inputMenu: {
      variants: {
        variant: {
          soft: 'text-highlighted bg-elevated/70 hover:bg-elevated focus:bg-elevated focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary focus-visible:outline-none disabled:bg-elevated/50 disabled:opacity-75 disabled:focus-visible:ring-0',
        },
      },
      defaultVariants: {
        size: 'md',
        color: 'primary',
        variant: 'soft',
      },
    },

    inputNumber: {
      slots: {
        // Override default inline-flex shrink-to-content so qty/money fill the dialog.
        root: 'relative flex w-full items-center',
      },
      variants: {
        variant: {
          soft: 'text-highlighted bg-elevated/70 hover:bg-elevated focus:bg-elevated focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary focus-visible:outline-none disabled:bg-elevated/50 disabled:opacity-75 disabled:focus-visible:ring-0',
        },
      },
      defaultVariants: {
        size: 'md',
        color: 'primary',
        variant: 'soft',
        increment: false,
        decrement: false,
      },
    },

    inputDate: {
      variants: {
        variant: {
          soft: 'text-highlighted bg-elevated/70 hover:bg-elevated has-focus:bg-elevated has-focus:ring-2 has-focus:ring-inset has-focus:ring-primary disabled:bg-elevated/50 disabled:opacity-75',
        },
      },
      defaultVariants: {
        size: 'md',
        color: 'primary',
        variant: 'soft',
      },
    },

    inputTime: {
      variants: {
        variant: {
          soft: 'text-highlighted bg-elevated/70 hover:bg-elevated has-focus:bg-elevated has-focus:ring-2 has-focus:ring-inset has-focus:ring-primary disabled:bg-elevated/50 disabled:opacity-75',
        },
      },
      defaultVariants: {
        size: 'md',
        color: 'primary',
        variant: 'soft',
      },
    },

    pinInput: {
      variants: {
        variant: {
          soft: 'text-highlighted bg-elevated/70 hover:bg-elevated focus:bg-elevated focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary focus-visible:outline-none disabled:bg-elevated/50 disabled:opacity-75 disabled:focus-visible:ring-0',
        },
      },
      defaultVariants: {
        size: 'md',
        color: 'primary',
        variant: 'soft',
      },
    },

    /** Checked state uses inverted (near-black) fill like the document form screenshot. */
    checkbox: {
      defaultVariants: {
        size: 'md',
        color: 'neutral',
        variant: 'list',
        indicator: 'start',
      },
    },

    switch: {
      defaultVariants: {
        size: 'md',
        color: 'neutral',
      },
    },

    /** Keep every horizontal tab group anchored to the left. */
    tabs: {
      slots: {
        root: 'items-start',
        list: 'justify-start',
      },
    },

    dashboardPanel: {
      slots: {
        // Keep main content inset consistent (reload + navigate)
        body: 'flex flex-col gap-0 flex-1 overflow-y-auto px-1.5 pt-1.5 pb-0',
      },
    },
    dashboardNavbar: {
      slots: {
        root: 'h-(--ui-header-height) shrink-0 flex items-center justify-between border-b border-default px-1.5 gap-1.5',
      },
    },
    modal: {
      compoundVariants: [
        {
          scrollable: true,
          fullscreen: false,
          class: {
            overlay: 'grid !place-items-start !justify-items-center p-4 !pt-[5vh] sm:!pt-[5vh]',
          },
        },
        {
          scrollable: false,
          fullscreen: false,
          class: {
            // Override default vertical center (top-1/2 -translate-y-1/2)
            content: '!top-[5%] left-1/2 !-translate-x-1/2 !translate-y-0 max-h-[calc(100dvh-8vh)] sm:max-h-[calc(100dvh-10vh)] overflow-hidden',
          },
        },
      ],
    },
  },
})


