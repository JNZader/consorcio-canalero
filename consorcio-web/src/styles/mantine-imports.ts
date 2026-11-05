/**
 * Único punto de entrada de CSS de Mantine.
 *
 * El bundle monolítico `@mantine/core/styles.css` arrastraba componentes
 * que esta app no renderiza (ColorPicker, Spotlight, Tour, …). Acá entran
 * la base (baseline, variables, global) y el CSS de cada componente usado,
 * más los internos que esos componentes montan sin importarlos
 * (Input, Combobox, Overlay, Popover, ModalBase, Pill).
 *
 * Dates y Dropzone siguen al lado del único componente que los usa.
 * Notifications conserva su CSS de paquete; la tarjeta vive en Notification.css.
 */

import '@mantine/core/styles/baseline.css';
import '@mantine/core/styles/default-css-variables.css';
import '@mantine/core/styles/global.css';

import '@mantine/core/styles/Accordion.css';
import '@mantine/core/styles/ActionIcon.css';
import '@mantine/core/styles/Alert.css';
import '@mantine/core/styles/Anchor.css';
import '@mantine/core/styles/AppShell.css';
import '@mantine/core/styles/Avatar.css';
import '@mantine/core/styles/Badge.css';
import '@mantine/core/styles/Burger.css';
import '@mantine/core/styles/Button.css';
import '@mantine/core/styles/Card.css';
import '@mantine/core/styles/Center.css';
import '@mantine/core/styles/Checkbox.css';
import '@mantine/core/styles/CheckboxIndicator.css';
import '@mantine/core/styles/CloseButton.css';
import '@mantine/core/styles/Code.css';
import '@mantine/core/styles/ColorSwatch.css';
import '@mantine/core/styles/Combobox.css';
import '@mantine/core/styles/Container.css';
import '@mantine/core/styles/Divider.css';
import '@mantine/core/styles/Drawer.css';
import '@mantine/core/styles/Flex.css';
import '@mantine/core/styles/FloatingIndicator.css';
import '@mantine/core/styles/Grid.css';
import '@mantine/core/styles/Group.css';
import '@mantine/core/styles/Image.css';
import '@mantine/core/styles/InlineInput.css';
import '@mantine/core/styles/Input.css';
import '@mantine/core/styles/List.css';
import '@mantine/core/styles/Loader.css';
import '@mantine/core/styles/LoadingOverlay.css';
import '@mantine/core/styles/Menu.css';
import '@mantine/core/styles/Modal.css';
import '@mantine/core/styles/ModalBase.css';
import '@mantine/core/styles/NavLink.css';
import '@mantine/core/styles/Notification.css';
import '@mantine/core/styles/NumberInput.css';
import '@mantine/core/styles/Overlay.css';
import '@mantine/core/styles/Pagination.css';
import '@mantine/core/styles/Paper.css';
import '@mantine/core/styles/PasswordInput.css';
import '@mantine/core/styles/Pill.css';
import '@mantine/core/styles/PillsInput.css';
import '@mantine/core/styles/Popover.css';
import '@mantine/core/styles/Progress.css';
import '@mantine/core/styles/Radio.css';
import '@mantine/core/styles/RadioIndicator.css';
import '@mantine/core/styles/ScrollArea.css';
import '@mantine/core/styles/SegmentedControl.css';
import '@mantine/core/styles/SimpleGrid.css';
import '@mantine/core/styles/Skeleton.css';
import '@mantine/core/styles/Slider.css';
import '@mantine/core/styles/Stack.css';
import '@mantine/core/styles/Switch.css';
import '@mantine/core/styles/Table.css';
import '@mantine/core/styles/Tabs.css';
import '@mantine/core/styles/Text.css';
import '@mantine/core/styles/ThemeIcon.css';
import '@mantine/core/styles/Timeline.css';
import '@mantine/core/styles/Title.css';
import '@mantine/core/styles/Tooltip.css';
import '@mantine/core/styles/UnstyledButton.css';
import '@mantine/core/styles/VisuallyHidden.css';

import '@mantine/notifications/styles.css';
